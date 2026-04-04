from pydantic import BaseModel, Field


class CandidateMoveInput(BaseModel):
    move: str = Field(min_length=2, max_length=20)
    note: str = Field(default='', max_length=1000)
    is_selected: bool = False
    eval_cp: float | None = None
    eval_source: str | None = Field(default=None, max_length=64)


class CandidateUpdateRequest(BaseModel):
    version: int
    candidates: list[CandidateMoveInput]


class CandidateMoveOut(BaseModel):
    move: str
    note: str
    is_selected: bool
    eval_cp: float | None = None
    eval_source: str | None = None


class CandidateUpdateResponse(BaseModel):
    session_id: str
    turn_id: str
    version: int
    state: str
    candidates: list[CandidateMoveOut]
