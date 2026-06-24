from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    APP_NAME: str = "distributed-rate-limiter"

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return value

    @field_validator("RATE_LIMIT_REQUESTS")
    @classmethod
    def validate_rate_limit_requests(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("RATE_LIMIT_REQUESTS must be greater than 0")
        return value

    @field_validator("RATE_LIMIT_WINDOW_SECONDS")
    @classmethod
    def validate_rate_limit_window_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be greater than 0")
        return value


settings = Settings()
