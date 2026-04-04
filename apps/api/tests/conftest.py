import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ['DATABASE_URL'] = 'sqlite:///./test_chess_app.db'
os.environ['ENGINE_WORKER_URL'] = 'http://127.0.0.1:8101'
os.environ['REFLECTION_WORKER_URL'] = 'http://127.0.0.1:8102'

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.session_service import SessionService  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def service(db_session):
    return SessionService(db_session)


@pytest.fixture
def user_id() -> str:
    return 'user-1001'
