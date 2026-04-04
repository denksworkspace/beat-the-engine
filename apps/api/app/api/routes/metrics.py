from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_user_id
from app.db.session import get_db
from app.schemas.metrics import MetricsResponse
from app.services.session_service import SessionService

router = APIRouter(prefix='/v1/metrics', tags=['metrics'])


@router.get('/users/{user_id}', response_model=MetricsResponse)
def get_metrics(
    user_id: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    db: Session = Depends(get_db),
    caller_user: str = Depends(get_user_id),
) -> dict:
    # MVP policy: users can only query their own metrics.
    if caller_user != user_id:
        user_id = caller_user
    service = SessionService(db)
    return service.get_metrics(user_id, start, end)
