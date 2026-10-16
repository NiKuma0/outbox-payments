"""Process configuration from environment variables (see ``.env.example``)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    database_pool_size: int = Field(default=10, ge=1)
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    api_key: SecretStr = SecretStr("dev-api-key")

    relay_batch_size: int = Field(default=100, ge=1)
    relay_poll_interval_seconds: float = Field(default=0.5, gt=0)
    outbox_retention_days: int = Field(default=7, ge=1)
    outbox_cleanup_interval_seconds: float = Field(default=3600, gt=0)

    consumer_prefetch_count: int = Field(default=10, ge=1)
    # Number of *retries* after the first delivery; 3 => 4 attempts in total.
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_base_delay_seconds: float = Field(default=1.0, gt=0)
    retry_backoff_factor: float = Field(default=4.0, ge=1)
    webhook_timeout_seconds: float = Field(default=5.0, gt=0)

    payment_min_delay_seconds: float = Field(default=2.0, ge=0)
    payment_max_delay_seconds: float = Field(default=5.0, ge=0)
    payment_success_rate: float = Field(default=0.9, ge=0, le=1)

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
