from __future__ import annotations

import os
import shutil
from contextlib import contextmanager

import chess
import chess.engine
from fastapi import FastAPI
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    fen: str
    selected_move: str = Field(min_length=2, max_length=20)
    engine_level: int = Field(default=5, ge=1, le=20)
    think_seconds: float | None = Field(default=None, gt=0.0, le=10.0)


class AnalyzeResponse(BaseModel):
    fen_after: str
    engine_move: str
    pv: str
    eval_before: float
    eval_after: float
    think_ms: int


class EvaluateRequest(BaseModel):
    fen: str
    engine_level: int = Field(default=5, ge=1, le=20)
    think_seconds: float | None = Field(default=None, gt=0.0, le=10.0)


class EvaluateResponse(BaseModel):
    eval_cp: float
    source: str


app = FastAPI(title='Chess Engine Worker', version='1.0.0')


def material_eval_cp(board: chess.Board) -> float:
    values = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    score = 0
    for piece, value in values.items():
        score += len(board.pieces(piece, chess.WHITE)) * value
        score -= len(board.pieces(piece, chess.BLACK)) * value
    # White perspective to match UI eval bar convention.
    return round(score * 100.0, 2)


def parse_move(board: chess.Board, move_text: str) -> chess.Move:
    try:
        return board.parse_san(move_text)
    except ValueError:
        pass
    move = chess.Move.from_uci(move_text)
    if move not in board.legal_moves:
        raise ValueError('Illegal move')
    return move


def _resolve_stockfish_path() -> str | None:
    configured = os.getenv('STOCKFISH_PATH')
    candidates = [
        configured,
        '/usr/games/stockfish',
        '/usr/bin/stockfish',
        shutil.which('stockfish'),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _analysis_depth(engine_level: int) -> int:
    return max(8, min(20, 6 + engine_level))


@contextmanager
def _open_engine() -> chess.engine.SimpleEngine:
    path = _resolve_stockfish_path()
    if not path:
        raise RuntimeError('Stockfish binary was not found.')

    engine = chess.engine.SimpleEngine.popen_uci(path)
    try:
        yield engine
    finally:
        engine.quit()


def _score_cp_white(info: chess.engine.InfoDict) -> float:
    score = info.get('score')
    if score is None:
        return 0.0
    cp = score.white().score(mate_score=100000)
    return float(cp if cp is not None else 0.0)


def _analysis_limit(engine_level: int, think_seconds: float | None) -> chess.engine.Limit:
    if think_seconds is not None:
        return chess.engine.Limit(time=think_seconds)
    depth = _analysis_depth(engine_level)
    return chess.engine.Limit(depth=depth)


def _stockfish_eval(board: chess.Board, engine_level: int, think_seconds: float | None = None) -> tuple[float, int]:
    limit = _analysis_limit(engine_level, think_seconds)
    with _open_engine() as engine:
        info = engine.analyse(board, limit)
    think_ms = int(float(info.get('time', 0.0)) * 1000)
    return _score_cp_white(info), max(think_ms, 0)


def _stockfish_best_move(board: chess.Board, engine_level: int, think_seconds: float | None = None) -> tuple[str, str]:
    if board.is_game_over():
        return '', ''

    limit = _analysis_limit(engine_level, think_seconds)
    with _open_engine() as engine:
        analysis = engine.analyse(board, limit, multipv=1)
        play = engine.play(board, limit)

    best_move = play.move.uci() if play.move else ''
    pv_moves = analysis.get('pv', []) if isinstance(analysis, dict) else []
    pv = ' '.join(m.uci() for m in pv_moves[:8]) if pv_moves else best_move
    return best_move, pv


def _fallback_eval(board: chess.Board) -> tuple[float, int]:
    return material_eval_cp(board), 0


def _fallback_best_move(board: chess.Board) -> tuple[str, str]:
    if board.is_game_over():
        return '', ''
    move = sorted(list(board.legal_moves), key=lambda m: m.uci())[0]
    uci = move.uci()
    return uci, uci


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.post('/evaluate', response_model=EvaluateResponse)
def evaluate(payload: EvaluateRequest) -> EvaluateResponse:
    board = chess.Board(payload.fen)

    try:
        eval_cp, _ = _stockfish_eval(board, payload.engine_level, payload.think_seconds)
        return EvaluateResponse(eval_cp=eval_cp, source='stockfish')
    except Exception:
        eval_cp, _ = _fallback_eval(board)
        return EvaluateResponse(eval_cp=eval_cp, source='material-fallback')


@app.post('/analyze', response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    board = chess.Board(payload.fen)

    try:
        eval_before, think_before = _stockfish_eval(board, payload.engine_level, payload.think_seconds)
        source = 'stockfish'
    except Exception:
        eval_before, think_before = _fallback_eval(board)
        source = 'material-fallback'

    move = parse_move(board, payload.selected_move)
    board.push(move)

    try:
        eval_after, think_after = _stockfish_eval(board, payload.engine_level, payload.think_seconds)
    except Exception:
        eval_after, think_after = _fallback_eval(board)
        source = 'material-fallback'

    if source == 'stockfish':
        try:
            engine_move, pv = _stockfish_best_move(board, payload.engine_level, payload.think_seconds)
        except Exception:
            engine_move, pv = _fallback_best_move(board)
    else:
        engine_move, pv = _fallback_best_move(board)

    if engine_move:
        board.push(chess.Move.from_uci(engine_move))

    return AnalyzeResponse(
        fen_after=board.fen(),
        engine_move=engine_move,
        pv=pv,
        eval_before=eval_before,
        eval_after=eval_after,
        think_ms=max(think_before, think_after),
    )
