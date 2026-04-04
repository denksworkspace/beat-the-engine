from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.base import (
    AIReflectionModel,
    CandidateMoveModel,
    CommittedMoveModel,
    EngineAnalysisModel,
    MetricsSnapshotModel,
    SessionModel,
    TurnModel,
)


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_session(self, user_id: str, engine_level: int, mode: str, fen: str) -> tuple[SessionModel, TurnModel]:
        session = SessionModel(user_id=user_id, engine_level=engine_level, mode=mode)
        turn = TurnModel(session=session, turn_number=1, fen_before=fen)
        self.db.add(session)
        self.db.add(turn)
        self.db.flush()
        return session, turn

    def get_session_for_user(self, session_id: str, user_id: str) -> SessionModel | None:
        stmt = (
            select(SessionModel)
            .where(SessionModel.id == session_id, SessionModel.user_id == user_id)
            .options(joinedload(SessionModel.turns))
        )
        return self.db.execute(stmt).scalars().unique().first()

    def get_turn(self, session_id: str, turn_id: str) -> TurnModel | None:
        stmt = (
            select(TurnModel)
            .where(TurnModel.id == turn_id, TurnModel.session_id == session_id)
            .options(joinedload(TurnModel.candidate_moves), joinedload(TurnModel.committed_move))
        )
        return self.db.execute(stmt).scalars().unique().first()

    def list_turns(self, session_id: str) -> list[TurnModel]:
        stmt = (
            select(TurnModel)
            .where(TurnModel.session_id == session_id)
            .order_by(TurnModel.turn_number.asc())
            .options(joinedload(TurnModel.committed_move))
        )
        return self.db.execute(stmt).scalars().unique().all()

    def get_active_turn(self, session_id: str) -> TurnModel | None:
        stmt = (
            select(TurnModel)
            .where(TurnModel.session_id == session_id)
            .order_by(TurnModel.turn_number.desc())
            .limit(1)
            .options(joinedload(TurnModel.committed_move), joinedload(TurnModel.candidate_moves))
        )
        return self.db.execute(stmt).scalars().unique().first()

    def replace_candidates(self, turn: TurnModel, candidates: list[dict]) -> list[CandidateMoveModel]:
        # Replace through the relationship itself so ORM state remains coherent
        # and deleted children do not linger in the in-memory collection.
        turn.candidate_moves.clear()
        self.db.flush()

        out: list[CandidateMoveModel] = []
        for item in candidates:
            candidate = CandidateMoveModel(
                move=item['move'],
                note=item.get('note', ''),
                is_selected=item.get('is_selected', False),
                eval_cp=item.get('eval_cp'),
                eval_source=item.get('eval_source'),
            )
            turn.candidate_moves.append(candidate)
            out.append(candidate)

        turn.version += 1
        self.db.flush()
        return out

    def create_committed_move(self, turn: TurnModel, move: str, reasoning_text: str) -> CommittedMoveModel:
        committed = CommittedMoveModel(turn=turn, move=move, reasoning_text=reasoning_text)
        self.db.add(committed)
        self.db.flush()
        return committed

    def create_engine_analysis(
        self,
        committed_move_id: str,
        engine_move: str,
        pv: str,
        eval_before: float,
        eval_after: float,
        think_ms: int,
    ) -> EngineAnalysisModel:
        analysis = EngineAnalysisModel(
            committed_move_id=committed_move_id,
            engine_move=engine_move,
            pv=pv,
            eval_before=eval_before,
            eval_after=eval_after,
            think_ms=think_ms,
        )
        self.db.add(analysis)
        self.db.flush()
        return analysis

    def create_reflection(
        self,
        committed_move_id: str,
        text: str,
        tags: list[str],
        better_move: str | None,
        status: str,
        model_version: str,
    ) -> AIReflectionModel:
        reflection = AIReflectionModel(
            committed_move_id=committed_move_id,
            text=text,
            tags=','.join(tags),
            better_move=better_move,
            status=status,
            model_version=model_version,
        )
        self.db.add(reflection)
        self.db.flush()
        return reflection

    def create_next_turn(self, session_id: str, turn_number: int, fen_before: str) -> TurnModel:
        next_turn = TurnModel(session_id=session_id, turn_number=turn_number, fen_before=fen_before)
        self.db.add(next_turn)
        self.db.flush()
        return next_turn

    def create_metrics_snapshot(self, session_id: str, turn_id: str, attempts_per_commit: float, eval_loss: float) -> None:
        snapshot = MetricsSnapshotModel(
            session_id=session_id,
            turn_id=turn_id,
            attempts_per_commit=attempts_per_commit,
            eval_loss=eval_loss,
        )
        self.db.add(snapshot)
        self.db.flush()

    def get_history(self, session_id: str, limit: int, offset: int) -> tuple[int, list[TurnModel]]:
        total_stmt = select(func.count()).select_from(TurnModel).where(TurnModel.session_id == session_id)
        total = self.db.execute(total_stmt).scalar_one()

        stmt = (
            select(TurnModel)
            .where(TurnModel.session_id == session_id)
            .order_by(TurnModel.turn_number.asc())
            .limit(limit)
            .offset(offset)
            .options(
                joinedload(TurnModel.candidate_moves),
                joinedload(TurnModel.committed_move).joinedload(CommittedMoveModel.engine_analysis),
                joinedload(TurnModel.committed_move).joinedload(CommittedMoveModel.reflection),
            )
        )
        turns = self.db.execute(stmt).scalars().unique().all()
        return total, turns

    def get_user_metrics(self, user_id: str, start: date | None, end: date | None) -> dict:
        session_stmt = select(SessionModel.id).where(SessionModel.user_id == user_id)
        session_ids = [r[0] for r in self.db.execute(session_stmt).all()]
        if not session_ids:
            return {
                'sessions': 0,
                'committed_turns': 0,
                'avg_candidates_per_commit': 0.0,
                'avg_eval_loss': 0.0,
                'reflection_tag_distribution': {},
                'model_version_distribution': {},
                'metrics_version': 'v1',
            }

        metrics_stmt = select(MetricsSnapshotModel).where(MetricsSnapshotModel.session_id.in_(session_ids))
        if start:
            metrics_stmt = metrics_stmt.where(func.date(MetricsSnapshotModel.created_at) >= start)
        if end:
            metrics_stmt = metrics_stmt.where(func.date(MetricsSnapshotModel.created_at) <= end)

        metrics = self.db.execute(metrics_stmt).scalars().all()

        reflection_stmt = (
            select(AIReflectionModel.tags, AIReflectionModel.model_version)
            .join(CommittedMoveModel, AIReflectionModel.committed_move_id == CommittedMoveModel.id)
            .join(TurnModel, CommittedMoveModel.turn_id == TurnModel.id)
            .where(TurnModel.session_id.in_(session_ids))
        )
        tags_rows = self.db.execute(reflection_stmt).all()

        tag_distribution: dict[str, int] = {}
        model_version_distribution: dict[str, int] = {}
        for row in tags_rows:
            raw = row[0] or ''
            model_version = str(row[1] or 'unknown').strip() or 'unknown'
            model_version_distribution[model_version] = model_version_distribution.get(model_version, 0) + 1
            for tag in [t for t in raw.split(',') if t]:
                tag_distribution[tag] = tag_distribution.get(tag, 0) + 1

        committed_turns = len(metrics)
        avg_candidates = sum(m.attempts_per_commit for m in metrics) / committed_turns if committed_turns else 0.0
        avg_eval_loss = sum(m.eval_loss for m in metrics) / committed_turns if committed_turns else 0.0

        return {
            'sessions': len(session_ids),
            'committed_turns': committed_turns,
            'avg_candidates_per_commit': round(avg_candidates, 3),
            'avg_eval_loss': round(avg_eval_loss, 3),
            'reflection_tag_distribution': tag_distribution,
            'model_version_distribution': model_version_distribution,
            'metrics_version': 'v1',
        }
