from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.candidate import CandidateMoveOut


STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


class CreateSessionRequest(BaseModel):
    engine_level: int = Field(default=5, ge=1, le=20)
    mode: Literal['standard', 'challenge'] = 'standard'
    fen: str = STARTING_FEN


class SessionCreateResponse(BaseModel):
    session_id: str
    turn_id: str
    fen: str
    mode: str
    engine_level: int


class SessionStateResponse(BaseModel):
    session_id: str
    user_id: str
    engine_level: int
    mode: str
    status: str
    active_turn_id: str
    turn_state: str
    turn_version: int
    fen: str
    candidates: list[CandidateMoveOut] = Field(default_factory=list)


class PositionEvalRequest(BaseModel):
    fen: str
    think_seconds: float = Field(default=0.25, ge=0.05, le=10.0)


class PositionEvalResponse(BaseModel):
    session_id: str
    turn_id: str
    fen: str
    eval_cp: float
    source: str


class UndoCommitResponse(BaseModel):
    session_id: str
    turn_id: str
    fen: str
    turn_version: int
