import chess
import pytest

from app.core.errors import AppError
from app.services.chess_rules import apply_move, legal_moves, parse_move


def test_apply_move_updates_fen() -> None:
    fen = chess.STARTING_FEN
    next_fen, move_uci = apply_move(fen, 'e2e4')
    assert move_uci == 'e2e4'
    assert next_fen != fen


def test_legal_moves_contains_known_opening_move() -> None:
    moves = legal_moves(chess.STARTING_FEN)
    assert 'e2e4' in moves


def test_parse_move_rejects_illegal_move() -> None:
    board = chess.Board(chess.STARTING_FEN)
    with pytest.raises(AppError) as exc:
        parse_move(board, 'e2e5')
    assert exc.value.code == 'ILLEGAL_MOVE'
