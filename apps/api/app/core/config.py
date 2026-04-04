from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'AI-Assisted Chess Reflection Training App API'
    app_env: str = 'dev'

    database_url: str = Field(
        default='postgresql+psycopg://postgres:postgres@localhost:5432/chess_app',
        alias='DATABASE_URL',
    )
    challenge_mode_enabled: bool = Field(default=True, alias='CHALLENGE_MODE_ENABLED')

    engine_worker_url: str = Field(default='http://localhost:8101', alias='ENGINE_WORKER_URL')
    reflection_worker_url: str = Field(default='http://localhost:8102', alias='REFLECTION_WORKER_URL')

    reflection_timeout_seconds: float = Field(default=3.0, alias='REFLECTION_TIMEOUT_SECONDS')
    max_reflection_length: int = Field(default=800, alias='MAX_REFLECTION_LENGTH')
    cors_allow_origins: str = Field(
        default='http://localhost:5173,http://127.0.0.1:5173',
        alias='CORS_ALLOW_ORIGINS',
    )

    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(',') if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
