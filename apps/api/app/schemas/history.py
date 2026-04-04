from pydantic import BaseModel, Field


class HistoryItem(BaseModel):
    turn_id: str
    turn_number: int
    committed_move: str
    candidate_count: int
    eval_before: float | None = None
    eval_after: float | None = None
    reflection_text: str | None = None
    reflection_tags: list[str] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    session_id: str
    total: int
    limit: int
    offset: int
    items: list[HistoryItem]
