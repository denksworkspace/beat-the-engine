from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
