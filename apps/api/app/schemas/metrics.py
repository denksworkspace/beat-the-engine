from pydantic import BaseModel


class MetricsResponse(BaseModel):
    user_id: str
    sessions: int
    committed_turns: int
    avg_candidates_per_commit: float
    avg_eval_loss: float
    reflection_tag_distribution: dict[str, int]
    model_version_distribution: dict[str, int]
    metrics_version: str
