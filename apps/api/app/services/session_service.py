from __future__ import annotations

from datetime import date

import chess
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.base import MetricsSnapshotModel, SessionModel, TurnModel
from app.repositories.session_repository import SessionRepository
from app.schemas.candidate import CandidateMoveInput, CandidateUpdateRequest
from app.schemas.commit import CommitMoveRequest
from app.services.chess_rules import legal_moves
from app.workers.engine_client import EngineWorkerClient
from app.workers.reflection_client import ReflectionWorkerClient


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SessionRepository(db)
        self.engine_client = EngineWorkerClient()
        self.reflection_client = ReflectionWorkerClient()
        self.settings = get_settings()

    def create_session(self, user_id: str, engine_level: int, mode: str, fen: str) -> dict:
        session, turn = self.repo.create_session(user_id=user_id, engine_level=engine_level, mode=mode, fen=fen)
        self.db.commit()
        return {
            'session_id': session.id,
            'turn_id': turn.id,
            'fen': turn.fen_before,
            'mode': session.mode,
            'engine_level': session.engine_level,
        }

    def get_session_state(self, user_id: str, session_id: str) -> dict:
        session = self._get_session(user_id, session_id)
        active_turn = self._get_active_turn(session.id)
        hydrated_turn = self.repo.get_turn(session.id, active_turn.id)
        if hydrated_turn:
            active_turn = hydrated_turn
        fen = active_turn.fen_after or active_turn.fen_before
        candidates = [
            {
                'move': candidate.move,
                'note': candidate.note,
                'is_selected': candidate.is_selected,
                'eval_cp': float(candidate.eval_cp) if candidate.eval_cp is not None else None,
                'eval_source': candidate.eval_source,
            }
            for candidate in active_turn.candidate_moves
        ]
        return {
            'session_id': session.id,
            'user_id': session.user_id,
            'engine_level': session.engine_level,
            'mode': session.mode,
            'status': session.status,
            'active_turn_id': active_turn.id,
            'turn_state': active_turn.state,
            'turn_version': active_turn.version,
            'fen': fen,
            'candidates': candidates,
        }

    def save_candidates(self, user_id: str, session_id: str, turn_id: str, payload: CandidateUpdateRequest) -> dict:
        self._get_session(user_id, session_id)
        turn = self._get_turn(session_id, turn_id)

        if turn.version != payload.version:
            raise AppError(
                'STALE_TURN',
                'Turn version mismatch; reload current turn before saving candidates.',
                409,
                {'expected_version': turn.version, 'received_version': payload.version},
            )

        self._validate_candidates(turn.fen_before, payload.candidates)
        stored = self.repo.replace_candidates(turn, [c.model_dump() for c in payload.candidates])
        turn.state = 'draft_exploration'
        self.db.commit()

        return {
            'session_id': session_id,
            'turn_id': turn.id,
            'version': turn.version,
            'state': turn.state,
            'candidates': [
                {
                    'move': candidate.move,
                    'note': candidate.note,
                    'is_selected': candidate.is_selected,
                    'eval_cp': float(candidate.eval_cp) if candidate.eval_cp is not None else None,
                    'eval_source': candidate.eval_source,
                }
                for candidate in stored
            ],
        }

    def commit_move(self, user_id: str, session_id: str, turn_id: str, payload: CommitMoveRequest) -> dict:
        session = self._get_session(user_id, session_id)
        turn = self._get_turn(session_id, turn_id)

        if turn.version != payload.version:
            raise AppError(
                'STALE_TURN',
                'Turn version mismatch; reload current turn before committing.',
                409,
                {'expected_version': turn.version, 'received_version': payload.version},
            )

        if turn.committed_move is not None:
            raise AppError('TURN_ALREADY_COMMITTED', 'Turn has already been committed.', 409)

        self._validate_selected_move(turn.fen_before, payload.selected_move)
        self._validate_challenge_requirements(session.mode, payload.reasoning_text, payload.challenge_answer)

        turn.state = 'move_committed'
        turn.version += 1
        committed = self.repo.create_committed_move(turn, payload.selected_move, payload.reasoning_text)

        analysis = self.engine_client.analyze(turn.fen_before, payload.selected_move, session.engine_level)
        analysis['selected_move'] = payload.selected_move
        engine = self.repo.create_engine_analysis(
            committed_move_id=committed.id,
            engine_move=analysis['engine_move'],
            pv=analysis.get('pv', ''),
            eval_before=float(analysis['eval_before']),
            eval_after=float(analysis['eval_after']),
            think_ms=int(analysis.get('think_ms', 250)),
        )

        reflection_payload = self.reflection_client.reflect(
            reasoning_text=payload.reasoning_text,
            analysis=analysis,
            challenge_mode=session.mode == 'challenge',
        )
        reflection = self.repo.create_reflection(
            committed_move_id=committed.id,
            text=reflection_payload['text'],
            tags=reflection_payload.get('tags', []),
            better_move=reflection_payload.get('better_move'),
            status=reflection_payload.get('status', 'available'),
            model_version=reflection_payload.get('model_version', 'local-v1'),
        )

        turn.fen_after = analysis['fen_after']
        turn.state = 'reflected'

        attempts = len(turn.candidate_moves)
        eval_loss = max(0.0, float(engine.eval_before) - float(engine.eval_after))
        self.repo.create_metrics_snapshot(session.id, turn.id, float(attempts), eval_loss)

        next_turn = self.repo.create_next_turn(
            session_id=session.id,
            turn_number=turn.turn_number + 1,
            fen_before=analysis['fen_after'],
        )

        self.db.commit()

        return {
            'session_id': session.id,
            'turn_id': turn.id,
            'next_turn_id': next_turn.id,
            'fen': analysis['fen_after'],
            'engine_move': engine.engine_move,
            'eval_before': float(engine.eval_before),
            'eval_after': float(engine.eval_after),
            'reflection': {
                'text': reflection.text,
                'tags': [x for x in reflection.tags.split(',') if x],
                'better_move': reflection.better_move,
                'status': reflection.status,
            },
            'metrics_snapshot': {
                'attempts_per_commit': float(attempts),
                'eval_loss': float(eval_loss),
            },
        }

    def evaluate_position(self, user_id: str, session_id: str, fen: str, think_seconds: float) -> dict:
        session = self._get_session(user_id, session_id)
        active_turn = self._get_active_turn(session.id)

        try:
            normalized_fen = chess.Board(fen).fen()
        except ValueError as exc:
            raise AppError('INVALID_FEN', 'Invalid FEN string for evaluation.', 400) from exc

        evaluation = self.engine_client.evaluate(normalized_fen, session.engine_level, think_seconds)
        return {
            'session_id': session.id,
            'turn_id': active_turn.id,
            'fen': normalized_fen,
            'eval_cp': float(evaluation['eval_cp']),
            'source': str(evaluation.get('source', 'unknown')),
        }

    def undo_last_commit(self, user_id: str, session_id: str) -> dict:
        session = self._get_session(user_id, session_id)
        turns = self.repo.list_turns(session.id)
        if not turns:
            raise AppError('TURN_NOT_FOUND', 'No turns found in session.', 404)

        latest_turn = turns[-1]
        previous_turn = turns[-2] if len(turns) >= 2 else None
        turn_to_restore: TurnModel

        if latest_turn.committed_move is not None:
            turn_to_restore = latest_turn
        elif previous_turn is not None and previous_turn.committed_move is not None:
            # Delete the auto-created draft turn so the restored committed turn becomes active again.
            self.db.delete(latest_turn)
            turn_to_restore = previous_turn
        else:
            raise AppError('NOTHING_TO_UNDO', 'No committed move available to undo.', 409)

        committed_move = turn_to_restore.committed_move
        if committed_move is None:
            raise AppError('NOTHING_TO_UNDO', 'No committed move available to undo.', 409)

        self.db.execute(
            delete(MetricsSnapshotModel).where(
                MetricsSnapshotModel.session_id == session.id,
                MetricsSnapshotModel.turn_id == turn_to_restore.id,
            )
        )
        # Relationship is configured with delete-orphan cascade, so unlinking is enough.
        turn_to_restore.committed_move = None
        turn_to_restore.fen_after = None
        turn_to_restore.state = 'draft_exploration'
        turn_to_restore.version += 1
        self.db.commit()
        self.db.expire_all()

        return {
            'session_id': session.id,
            'turn_id': turn_to_restore.id,
            'fen': turn_to_restore.fen_before,
            'turn_version': turn_to_restore.version,
        }

    def get_history(self, user_id: str, session_id: str, limit: int, offset: int) -> dict:
        self._get_session(user_id, session_id)
        total, turns = self.repo.get_history(session_id=session_id, limit=limit, offset=offset)
        items: list[dict] = []

        for turn in turns:
            if not turn.committed_move:
                continue
            reflection_tags: list[str] = []
            reflection_text = None
            eval_before = None
            eval_after = None

            if turn.committed_move.engine_analysis:
                eval_before = float(turn.committed_move.engine_analysis.eval_before)
                eval_after = float(turn.committed_move.engine_analysis.eval_after)
            if turn.committed_move.reflection:
                reflection_text = turn.committed_move.reflection.text
                reflection_tags = [x for x in turn.committed_move.reflection.tags.split(',') if x]

            items.append(
                {
                    'turn_id': turn.id,
                    'turn_number': turn.turn_number,
                    'committed_move': turn.committed_move.move,
                    'candidate_count': len(turn.candidate_moves),
                    'eval_before': eval_before,
                    'eval_after': eval_after,
                    'reflection_text': reflection_text,
                    'reflection_tags': reflection_tags,
                }
            )

        return {'session_id': session_id, 'total': total, 'limit': limit, 'offset': offset, 'items': items}

    def get_metrics(self, user_id: str, start: date | None, end: date | None) -> dict:
        metrics = self.repo.get_user_metrics(user_id=user_id, start=start, end=end)
        return {'user_id': user_id, **metrics}

    def _get_session(self, user_id: str, session_id: str) -> SessionModel:
        session = self.repo.get_session_for_user(session_id=session_id, user_id=user_id)
        if not session:
            raise AppError('SESSION_NOT_FOUND', 'Session not found for user.', 404)
        return session

    def _get_turn(self, session_id: str, turn_id: str) -> TurnModel:
        turn = self.repo.get_turn(session_id=session_id, turn_id=turn_id)
        if not turn:
            raise AppError('TURN_NOT_FOUND', 'Turn not found in session.', 404)
        return turn

    def _get_active_turn(self, session_id: str) -> TurnModel:
        active_turn = self.repo.get_active_turn(session_id)
        if not active_turn:
            raise AppError('TURN_NOT_FOUND', 'No turns found in session.', 404)
        return active_turn

    def _validate_selected_move(self, fen: str, move: str) -> None:
        if move not in legal_moves(fen):
            raise AppError('ILLEGAL_MOVE', f'Illegal move for current position: {move}', 400)

    def _validate_candidates(self, fen: str, candidates: list[CandidateMoveInput]) -> None:
        legal = legal_moves(fen)
        for candidate in candidates:
            if candidate.move not in legal:
                raise AppError('ILLEGAL_MOVE', f'Illegal candidate move: {candidate.move}', 400)

    def _validate_challenge_requirements(self, mode: str, reasoning_text: str, challenge_answer: str | None) -> None:
        if mode != 'challenge' or not self.settings.challenge_mode_enabled:
            return
        normalized = (reasoning_text or '').strip()
        answer = (challenge_answer or '').strip()
        if len(normalized) >= 20:
            return
        if answer:
            return
        raise AppError(
            'CHALLENGE_REQUIRED',
            'Reasoning is too short for challenge mode.',
            422,
            {
                'prompt': 'What tactical or positional idea supports this move? Provide at least one concrete line.',
                'min_reasoning_chars': 20,
            },
        )
