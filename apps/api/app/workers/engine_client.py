from __future__ import annotations

import chess
import httpx

from app.core.config import get_settings
from app.services.chess_rules import parse_move


def _material_eval_white_cp(fen: str) -> float:
    board = chess.Board(fen)
    values = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    score = 0
    for piece_type, value in values.items():
        score += len(board.pieces(piece_type, chess.WHITE)) * value
        score -= len(board.pieces(piece_type, chess.BLACK)) * value
    return round(score * 100.0, 2)


class EngineWorkerClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _timeout_seconds(self, think_seconds: float | None) -> float:
        if think_seconds is None:
            return 6.0
        return max(6.0, think_seconds + 1.0)

    def analyze(self, fen: str, selected_move: str, engine_level: int, think_seconds: float | None = None) -> dict:
        payload = {'fen': fen, 'selected_move': selected_move, 'engine_level': engine_level}
        if think_seconds is not None:
            payload['think_seconds'] = think_seconds
        try:
            with httpx.Client(timeout=self._timeout_seconds(think_seconds)) as client:
                response = client.post(f'{self.settings.engine_worker_url}/analyze', json=payload)
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        return self._local_analyze(fen, selected_move)

    def evaluate(self, fen: str, engine_level: int, think_seconds: float | None = None) -> dict:
        payload = {'fen': fen, 'engine_level': engine_level}
        if think_seconds is not None:
            payload['think_seconds'] = think_seconds
        try:
            with httpx.Client(timeout=self._timeout_seconds(think_seconds)) as client:
                response = client.post(f'{self.settings.engine_worker_url}/evaluate', json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return {'eval_cp': float(data.get('eval_cp', 0.0)), 'source': data.get('source', 'stockfish')}
        except Exception:
            pass
        return {'eval_cp': _material_eval_white_cp(fen), 'source': 'material-fallback'}

    def _local_analyze(self, fen: str, selected_move: str) -> dict:
        board = chess.Board(fen)
        eval_before = _material_eval_white_cp(board.fen())

        move = parse_move(board, selected_move)
        board.push(move)
        eval_after = _material_eval_white_cp(board.fen())

        if board.is_game_over():
            engine_move = ''
            pv = ''
        else:
            engine_choice = sorted(list(board.legal_moves), key=lambda m: m.uci())[0]
            engine_move = engine_choice.uci()
            pv = engine_move
            board.push(engine_choice)

        return {
            'fen_after': board.fen(),
            'engine_move': engine_move,
            'pv': pv,
            'eval_before': eval_before,
            'eval_after': eval_after,
            'think_ms': 250,
        }
