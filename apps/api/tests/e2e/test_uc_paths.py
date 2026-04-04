import chess

from app.schemas.candidate import CandidateMoveInput, CandidateUpdateRequest
from app.schemas.commit import CommitMoveRequest
from app.schemas.session import CreateSessionRequest


def _pick(fen: str) -> str:
    board = chess.Board(fen)
    return sorted([m.uci() for m in board.legal_moves])[0]


def test_uc11_uc21_uc31_end_to_end(service, user_id) -> None:
    # UC-1.1 start game
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)

    # UC-1.2 candidate drafting
    move = _pick(created['fen'])
    saved = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[
                CandidateMoveInput(move=move, note='Candidate A', is_selected=True),
                CandidateMoveInput(move=move, note='Candidate B revised', is_selected=False),
            ],
        ),
    )
    assert saved['state'] == 'draft_exploration'

    # UC-2.1 commit + reflection
    committed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='Improve initiative and reduce tactical risk around my king.',
            version=2,
        ),
    )
    assert committed['reflection']['text']

    # UC-3.1 history review
    history = service.get_history(user_id, created['session_id'], limit=10, offset=0)
    assert len(history['items']) >= 1
