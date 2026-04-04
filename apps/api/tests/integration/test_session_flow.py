import chess

from app.core.errors import AppError
from app.schemas.candidate import CandidateMoveInput, CandidateUpdateRequest
from app.schemas.commit import CommitMoveRequest
from app.schemas.session import CreateSessionRequest
from app.workers.reflection_client import ReflectionWorkerClient


def _pick_legal_move(fen: str) -> str:
    board = chess.Board(fen)
    return sorted([m.uci() for m in board.legal_moves])[0]


def test_create_save_commit_history_and_metrics(service, user_id) -> None:
    created = service.create_session(
        user_id,
        CreateSessionRequest(engine_level=5, mode='standard').engine_level,
        CreateSessionRequest(engine_level=5, mode='standard').mode,
        CreateSessionRequest(engine_level=5, mode='standard').fen,
    )

    move = _pick_legal_move(created['fen'])
    saved = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[
                CandidateMoveInput(move=move, note='Control center and open lines.', is_selected=True),
            ],
        ),
    )
    assert saved['version'] == 2

    committed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='I want to improve central control and activate minor pieces.',
            version=2,
        ),
    )
    assert committed['next_turn_id'] != created['turn_id']
    assert isinstance(committed['reflection']['tags'], list)
    expected_board = chess.Board(created['fen'])
    expected_board.push(chess.Move.from_uci(move))
    if committed['engine_move']:
        expected_board.push(chess.Move.from_uci(committed['engine_move']))
    assert committed['fen'] == expected_board.fen()

    history = service.get_history(user_id, created['session_id'], limit=20, offset=0)
    assert history['total'] >= 2
    assert len(history['items']) == 1

    metrics = service.get_metrics(user_id, start=None, end=None)
    assert metrics['committed_turns'] == 1
    assert metrics['sessions'] == 1


def test_default_session_starts_from_classical_initial_position(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)
    assert created['fen'] == chess.STARTING_FEN


def test_illegal_move_rejected_on_commit(service, user_id) -> None:
    created = service.create_session(user_id, 3, 'standard', CreateSessionRequest().fen)

    move = _pick_legal_move(created['fen'])
    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='test', is_selected=True)],
        ),
    )

    try:
        service.commit_move(
            user_id,
            created['session_id'],
            created['turn_id'],
            CommitMoveRequest(selected_move='a1a1', reasoning_text='test', version=2),
        )
        assert False, 'Expected AppError'
    except AppError as exc:
        assert exc.code == 'ILLEGAL_MOVE'


def test_stale_turn_rejected(service, user_id) -> None:
    created = service.create_session(user_id, 3, 'standard', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='test', is_selected=True)],
        ),
    )

    try:
        service.commit_move(
            user_id,
            created['session_id'],
            created['turn_id'],
            CommitMoveRequest(selected_move=move, reasoning_text='old version', version=1),
        )
        assert False, 'Expected AppError'
    except AppError as exc:
        assert exc.code == 'STALE_TURN'


def test_challenge_mode_requires_reasoning_or_answer(service, user_id) -> None:
    created = service.create_session(user_id, 4, 'challenge', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='short', is_selected=True)],
        ),
    )

    try:
        service.commit_move(
            user_id,
            created['session_id'],
            created['turn_id'],
            CommitMoveRequest(selected_move=move, reasoning_text='short', version=2),
        )
        assert False, 'Expected AppError'
    except AppError as exc:
        assert exc.code == 'CHALLENGE_REQUIRED'

    allowed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='short',
            challenge_answer='I calculated recapture and king safety after exchanges.',
            version=2,
        ),
    )
    assert allowed['turn_id'] == created['turn_id']


def test_challenge_mode_gate_can_be_disabled_by_feature_flag(service, user_id) -> None:
    service.settings.challenge_mode_enabled = False
    created = service.create_session(user_id, 4, 'challenge', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])
    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='short', is_selected=True)],
        ),
    )

    committed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(selected_move=move, reasoning_text='short', version=2),
    )
    assert committed['turn_id'] == created['turn_id']


def test_commit_fails_open_when_reflection_service_is_unavailable(service, user_id, monkeypatch) -> None:
    created = service.create_session(user_id, 4, 'standard', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    def _unavailable(self, reasoning_text, analysis, challenge_mode):  # type: ignore[no-untyped-def]
        return {
            'text': 'Reflection unavailable. Commit still accepted.',
            'tags': ['fallback'],
            'better_move': None,
            'status': 'unavailable',
        }

    monkeypatch.setattr(ReflectionWorkerClient, 'reflect', _unavailable)

    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='line', is_selected=True)],
        ),
    )

    committed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='Some explanation for this move.',
            version=2,
        ),
    )
    assert committed['reflection']['status'] == 'unavailable'


def test_evaluate_position_with_session_stockfish_or_fallback(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)

    evaluated = service.evaluate_position(user_id, created['session_id'], created['fen'], 0.25)
    assert evaluated['session_id'] == created['session_id']
    assert evaluated['turn_id'] == created['turn_id']
    assert isinstance(evaluated['eval_cp'], float)
    assert evaluated['source'] in {'stockfish', 'material-fallback'}

    try:
        service.evaluate_position(user_id, created['session_id'], 'invalid fen', 0.25)
        assert False, 'Expected AppError'
    except AppError as exc:
        assert exc.code == 'INVALID_FEN'


def test_undo_last_commit_restores_previous_turn(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='line', is_selected=True)],
        ),
    )
    service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='Candidate line.',
            version=2,
        ),
    )

    undone = service.undo_last_commit(user_id, created['session_id'])
    assert undone['turn_id'] == created['turn_id']
    assert undone['fen'] == created['fen']


def test_multiple_candidate_replacements_then_commit(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    first = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[
                CandidateMoveInput(move=move, note='First draft', is_selected=False),
                CandidateMoveInput(move=move, note='Second draft', is_selected=True),
            ],
        ),
    )
    assert first['version'] == 2

    second = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=2,
            candidates=[CandidateMoveInput(move=move, note='Final draft', is_selected=True)],
        ),
    )
    assert second['version'] == 3
    assert len(second['candidates']) == 1

    committed = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(
            selected_move=move,
            reasoning_text='Finalize candidate and commit.',
            version=3,
        ),
    )
    assert committed['turn_id'] == created['turn_id']


def test_session_state_returns_persisted_candidate_notes(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)
    move = _pick_legal_move(created['fen'])

    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[CandidateMoveInput(move=move, note='Keep tension in the center.', is_selected=True)],
        ),
    )

    state = service.get_session_state(user_id, created['session_id'])
    assert len(state['candidates']) == 1
    assert state['candidates'][0]['move'] == move
    assert state['candidates'][0]['note'] == 'Keep tension in the center.'


def test_candidate_grades_persist_across_multiple_saves(service, user_id) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)
    board = chess.Board(created['fen'])
    moves = sorted([m.uci() for m in board.legal_moves])
    move_a = moves[0]
    move_b = moves[1]

    first = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=1,
            candidates=[
                CandidateMoveInput(
                    move=move_a,
                    note='Candidate A',
                    is_selected=True,
                    eval_cp=35.0,
                    eval_source='stockfish',
                ),
            ],
        ),
    )
    assert first['candidates'][0]['eval_cp'] == 35.0
    assert first['candidates'][0]['eval_source'] == 'stockfish'

    second = service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(
            version=2,
            candidates=[
                CandidateMoveInput(
                    move=move_a,
                    note='Candidate A',
                    is_selected=False,
                    eval_cp=35.0,
                    eval_source='stockfish',
                ),
                CandidateMoveInput(
                    move=move_b,
                    note='Candidate B',
                    is_selected=True,
                    eval_cp=-20.0,
                    eval_source='stockfish',
                ),
            ],
        ),
    )

    assert len(second['candidates']) == 2
    by_move = {candidate['move']: candidate for candidate in second['candidates']}
    assert by_move[move_a]['eval_cp'] == 35.0
    assert by_move[move_b]['eval_cp'] == -20.0

    state = service.get_session_state(user_id, created['session_id'])
    state_by_move = {candidate['move']: candidate for candidate in state['candidates']}
    assert state_by_move[move_a]['eval_cp'] == 35.0
    assert state_by_move[move_a]['eval_source'] == 'stockfish'
    assert state_by_move[move_b]['eval_cp'] == -20.0
    assert state_by_move[move_b]['eval_source'] == 'stockfish'


def test_metrics_include_model_version_distribution_and_are_stable(service, user_id, monkeypatch) -> None:
    created = service.create_session(user_id, 5, 'standard', CreateSessionRequest().fen)

    responses = [
        {'text': 'First', 'tags': ['tactic'], 'better_move': None, 'status': 'available', 'model_version': 'gpt-v1'},
        {'text': 'Second', 'tags': ['positional'], 'better_move': None, 'status': 'available', 'model_version': 'gpt-v2'},
    ]

    def _reflect(self, reasoning_text, analysis, challenge_mode):  # type: ignore[no-untyped-def]
        return responses.pop(0)

    monkeypatch.setattr(ReflectionWorkerClient, 'reflect', _reflect)

    move1 = _pick_legal_move(created['fen'])
    service.save_candidates(
        user_id,
        created['session_id'],
        created['turn_id'],
        CandidateUpdateRequest(version=1, candidates=[CandidateMoveInput(move=move1, note='line 1', is_selected=True)]),
    )
    first_commit = service.commit_move(
        user_id,
        created['session_id'],
        created['turn_id'],
        CommitMoveRequest(selected_move=move1, reasoning_text='line 1', version=2),
    )

    move2 = _pick_legal_move(first_commit['fen'])
    service.save_candidates(
        user_id,
        created['session_id'],
        first_commit['next_turn_id'],
        CandidateUpdateRequest(version=1, candidates=[CandidateMoveInput(move=move2, note='line 2', is_selected=True)]),
    )
    service.commit_move(
        user_id,
        created['session_id'],
        first_commit['next_turn_id'],
        CommitMoveRequest(selected_move=move2, reasoning_text='line 2', version=2),
    )

    metrics = service.get_metrics(user_id, start=None, end=None)
    assert metrics['committed_turns'] == 2
    assert metrics['metrics_version'] == 'v1'
    assert metrics['model_version_distribution']['gpt-v1'] == 1
    assert metrics['model_version_distribution']['gpt-v2'] == 1
