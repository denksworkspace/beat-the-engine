from __future__ import annotations

import chess

from app.core.errors import AppError


def parse_move(board: chess.Board, move_text: str) -> chess.Move:
    move_text = move_text.strip()
    try:
        return board.parse_san(move_text)
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(move_text)
    except ValueError as exc:
        raise AppError('ILLEGAL_MOVE', f'Invalid move format: {move_text}', 400) from exc
    if move not in board.legal_moves:
        raise AppError('ILLEGAL_MOVE', f'Illegal move for current position: {move_text}', 400)
    return move


def apply_move(fen: str, move_text: str) -> tuple[str, str]:
    board = chess.Board(fen)
    move = parse_move(board, move_text)
    board.push(move)
    return board.fen(), move.uci()


def legal_moves(fen: str) -> set[str]:
    board = chess.Board(fen)
    return {m.uci() for m in board.legal_moves}


def material_eval_cp(fen: str) -> float:
    board = chess.Board(fen)
    piece_values = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
    }
    score = 0
    for piece_type, value in piece_values.items():
        score += len(board.pieces(piece_type, chess.WHITE)) * value
        score -= len(board.pieces(piece_type, chess.BLACK)) * value
    # perspective of side to move
    if board.turn == chess.BLACK:
        score = -score
    return round(score * 100.0, 2)
