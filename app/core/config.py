from __future__ import annotations

from functools import cached_property

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения, читаемая из переменных окружения или .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    rate_limit_create: str = "10/minute"

    postgres_user: str = "booking"
    postgres_password: str = "booking"
    postgres_db: str = "booking"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # Если задан явный DATABASE_URL — используем его, иначе собираем из частей.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Вероятность сбоя mock-вызова внешнего сервиса в воркере.
    worker_failure_rate: float = 0.15
    # Сколько раз ретраить транзиентную ошибку перед тем, как помечать failed.
    worker_max_retries: int = 3

    @computed_field  
    @cached_property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
