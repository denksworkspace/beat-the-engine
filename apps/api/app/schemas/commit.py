from pydantic import BaseModel, Field


class CommitMoveRequest(BaseModel):
    selected_move: str = Field(min_length=2, max_length=20)
    reasoning_text: str = Field(default='', max_length=2000)
    version: int
    challenge_answer: str | None = Field(default=None, max_length=1000)


class ReflectionOut(BaseModel):
    text: str
    tags: list[str]
    better_move: str | None = None
    status: str = 'available'


class TurnResultResponse(BaseModel):
    session_id: str
    turn_id: str
    next_turn_id: str
    fen: str
    engine_move: str
    eval_before: float
    eval_after: float
    reflection: ReflectionOut
    metrics_snapshot: dict
