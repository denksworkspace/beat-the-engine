from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class SessionModel(Base):
    __tablename__ = 'sessions'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    engine_level: Mapped[int] = mapped_column(Integer, default=5)
    mode: Mapped[str] = mapped_column(String(32), default='standard')
    status: Mapped[str] = mapped_column(String(32), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    turns: Mapped[list[TurnModel]] = relationship(back_populates='session', cascade='all, delete-orphan')
    metric_snapshots: Mapped[list[MetricsSnapshotModel]] = relationship(
        back_populates='session', cascade='all, delete-orphan'
    )


class TurnModel(Base):
    __tablename__ = 'turns'
    __table_args__ = (UniqueConstraint('session_id', 'turn_number', name='uq_session_turn_number'),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'), index=True)
    turn_number: Mapped[int] = mapped_column(Integer, default=1)
    fen_before: Mapped[str] = mapped_column(Text)
    fen_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default='draft_exploration')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[SessionModel] = relationship(back_populates='turns')
    candidate_moves: Mapped[list[CandidateMoveModel]] = relationship(
        back_populates='turn', cascade='all, delete-orphan'
    )
    committed_move: Mapped[CommittedMoveModel | None] = relationship(
        back_populates='turn', cascade='all, delete-orphan', uselist=False
    )


class CandidateMoveModel(Base):
    __tablename__ = 'candidate_moves'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'), index=True)
    move: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(1000), default='')
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    eval_cp: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    turn: Mapped[TurnModel] = relationship(back_populates='candidate_moves')


class CommittedMoveModel(Base):
    __tablename__ = 'committed_moves'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'), unique=True, index=True)
    move: Mapped[str] = mapped_column(String(20))
    reasoning_text: Mapped[str] = mapped_column(String(2000), default='')
    committed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    turn: Mapped[TurnModel] = relationship(back_populates='committed_move')
    engine_analysis: Mapped[EngineAnalysisModel | None] = relationship(
        back_populates='committed_move', cascade='all, delete-orphan', uselist=False
    )
    reflection: Mapped[AIReflectionModel | None] = relationship(
        back_populates='committed_move', cascade='all, delete-orphan', uselist=False
    )


class EngineAnalysisModel(Base):
    __tablename__ = 'engine_analyses'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    committed_move_id: Mapped[str] = mapped_column(ForeignKey('committed_moves.id'), unique=True, index=True)
    engine_move: Mapped[str] = mapped_column(String(20))
    pv: Mapped[str] = mapped_column(String(255), default='')
    eval_before: Mapped[float] = mapped_column(Float)
    eval_after: Mapped[float] = mapped_column(Float)
    think_ms: Mapped[int] = mapped_column(Integer, default=250)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    committed_move: Mapped[CommittedMoveModel] = relationship(back_populates='engine_analysis')


class AIReflectionModel(Base):
    __tablename__ = 'ai_reflections'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    committed_move_id: Mapped[str] = mapped_column(ForeignKey('committed_moves.id'), unique=True, index=True)
    text: Mapped[str] = mapped_column(String(2000), default='')
    tags: Mapped[str] = mapped_column(String(255), default='')
    better_move: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default='available')
    model_version: Mapped[str] = mapped_column(String(64), default='local-v1')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    committed_move: Mapped[CommittedMoveModel] = relationship(back_populates='reflection')


class MetricsSnapshotModel(Base):
    __tablename__ = 'metrics_snapshots'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'), index=True)
    attempts_per_commit: Mapped[float] = mapped_column(Float)
    eval_loss: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[SessionModel] = relationship(back_populates='metric_snapshots')
