from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_user_id
from app.db.session import get_db
from app.schemas.candidate import CandidateUpdateRequest, CandidateUpdateResponse
from app.schemas.commit import CommitMoveRequest, TurnResultResponse
from app.schemas.history import HistoryResponse
from app.schemas.session import (
    CreateSessionRequest,
    PositionEvalRequest,
    PositionEvalResponse,
    SessionCreateResponse,
    SessionStateResponse,
    UndoCommitResponse,
)
from app.services.session_service import SessionService

router = APIRouter(prefix='/v1/sessions', tags=['sessions'])


@router.post('', response_model=SessionCreateResponse)
def create_session(
    payload: CreateSessionRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.create_session(user_id, payload.engine_level, payload.mode, payload.fen)


@router.get('/{session_id}', response_model=SessionStateResponse)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.get_session_state(user_id, session_id)


@router.put('/{session_id}/turns/{turn_id}/candidates', response_model=CandidateUpdateResponse)
def save_candidates(
    session_id: str,
    turn_id: str,
    payload: CandidateUpdateRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.save_candidates(user_id, session_id, turn_id, payload)


@router.post('/{session_id}/turns/{turn_id}/commit', response_model=TurnResultResponse)
def commit_move(
    session_id: str,
    turn_id: str,
    payload: CommitMoveRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.commit_move(user_id, session_id, turn_id, payload)


@router.post('/{session_id}/evaluate', response_model=PositionEvalResponse)
def evaluate_position(
    session_id: str,
    payload: PositionEvalRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.evaluate_position(user_id, session_id, payload.fen, payload.think_seconds)


@router.post('/{session_id}/undo', response_model=UndoCommitResponse)
def undo_last_commit(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.undo_last_commit(user_id, session_id)


@router.get('/{session_id}/history', response_model=HistoryResponse)
def get_history(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> dict:
    service = SessionService(db)
    return service.get_history(user_id, session_id, limit, offset)
