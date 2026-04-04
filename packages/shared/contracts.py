from pydantic import BaseModel, Field


class EngineAnalyzeRequest(BaseModel):
    fen: str
    selected_move: str = Field(min_length=2, max_length=20)
    engine_level: int = Field(ge=1, le=20)


class EngineAnalyzeResponse(BaseModel):
    fen_after: str
    engine_move: str
    pv: str
    eval_before: float
    eval_after: float
    think_ms: int


class ReflectionRequest(BaseModel):
    reasoning_text: str
    eval_before: float
    eval_after: float
    pv: str
    challenge_mode: bool


class ReflectionResponse(BaseModel):
    text: str
    tags: list[str]
    better_move: str | None = None
    status: str
