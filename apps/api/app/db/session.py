import time
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

settings = get_settings()
connect_args = {'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def _ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        table_names = set(inspector.get_table_names())

        if 'ai_reflections' in table_names:
            reflection_columns = {column['name'] for column in inspector.get_columns('ai_reflections')}
            if 'model_version' not in reflection_columns:
                connection.execute(text("ALTER TABLE ai_reflections ADD COLUMN model_version VARCHAR(64)"))
                connection.execute(
                    text(
                        "UPDATE ai_reflections SET model_version = 'local-v1' "
                        "WHERE model_version IS NULL OR model_version = ''"
                    )
                )
                if engine.dialect.name == 'postgresql':
                    connection.execute(text('ALTER TABLE ai_reflections ALTER COLUMN model_version SET NOT NULL'))

        if 'candidate_moves' in table_names:
            candidate_columns = {column['name'] for column in inspector.get_columns('candidate_moves')}
            if 'eval_cp' not in candidate_columns:
                connection.execute(text('ALTER TABLE candidate_moves ADD COLUMN eval_cp FLOAT'))
            if 'eval_source' not in candidate_columns:
                connection.execute(text('ALTER TABLE candidate_moves ADD COLUMN eval_source VARCHAR(64)'))


def init_db(max_attempts: int = 20, delay_seconds: float = 1.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_schema_compatibility()
            return
        except OperationalError:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
