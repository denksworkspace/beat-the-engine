from fastapi import Header

from app.core.errors import AppError


def get_user_id(x_user_id: str | None = Header(default=None)) -> str:
    if not x_user_id:
        raise AppError('AUTH_FAILED', 'Missing X-User-Id header.', 401)
    return x_user_id
