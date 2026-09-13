from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    instance_id: str = "instance-1"

    database_url: str = "postgresql+asyncpg://notify:notify@localhost:5432/notifications"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    ws_ticket_ttl_seconds: int = 10

    presence_ttl_seconds: int = 30
    heartbeat_interval_seconds: int = 15

    backlog_limit: int = 100

    rate_limit_messages: int = 50
    rate_limit_window_seconds: int = 10

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
