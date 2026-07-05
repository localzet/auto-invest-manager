from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+asyncpg://auto_invest:change-me@localhost:5432/auto_invest"
    redis_url: str = "redis://localhost:6379/0"
    enable_real_trading: bool = False
    global_kill_switch: bool = True
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    broker_provider: Literal["mock", "tinvest"] = "mock"
    tinvest_token: SecretStr | None = None
    tinvest_sandbox_token: SecretStr | None = None
    tinvest_account_id: str | None = None
    tinvest_target: Literal["prod", "sandbox"] = "sandbox"
    admin_api_key: Annotated[SecretStr, Field(min_length=32)] | None = None
    market_price_max_age_seconds: int = Field(default=60, gt=0, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
