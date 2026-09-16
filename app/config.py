from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    instance_id: str = "instance-1"

    database_url: str = "postgresql+asyncpg://notify:notify@localhost:5432/notifications"
    db_pool_size: int = 10
    db_pool_max_overflow: int = 20
    db_pool_timeout_seconds: int = 5

    redis_url: str = "redis://localhost:6379/0"
    health_check_timeout_seconds: float = 3.0

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    ws_ticket_ttl_seconds: int = 10

    presence_ttl_seconds: int = 30
    heartbeat_interval_seconds: int = 15

    instance_liveness_ttl_seconds: int = 15

    backlog_limit: int = 100

    rate_limit_messages: int = 50
    rate_limit_window_seconds: int = 10

    api_rate_limit_requests: int = 100
    api_rate_limit_window_seconds: int = 10

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
