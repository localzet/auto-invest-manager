from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, model_validator
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
    telegram_notifications_enabled: bool = False
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    automation_scheduler_enabled: bool = False
    automation_cycle_interval_seconds: int = Field(default=900, ge=60)
    automation_cycle_jitter_seconds: int = Field(default=30, ge=0, le=300)
    automation_lock_ttl_seconds: int = Field(default=1800, ge=60)
    automation_run_timeout_seconds: int = Field(default=600, ge=30)
    account_sync_interval_seconds: int = Field(default=300, ge=60)
    instrument_sync_interval_seconds: int = Field(default=86400, ge=300)
    stale_run_threshold_seconds: int = Field(default=1200, ge=60)
    broker_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    broker_retry_base_delay_seconds: float = Field(default=1.0, gt=0, le=10)
    broker_retry_max_delay_seconds: float = Field(default=20.0, gt=0, le=60)
    broker_streams_enabled: bool = False
    portfolio_stream_enabled: bool = True
    positions_stream_enabled: bool = True
    trades_stream_enabled: bool = True
    stream_automation_trigger_enabled: bool = False
    broker_stream_lock_ttl_seconds: int = Field(default=120, ge=30, le=3600)
    broker_stream_lock_renew_interval_seconds: int = Field(default=30, ge=5, le=600)
    broker_stream_reconnect_initial_seconds: float = Field(default=1, gt=0, le=30)
    broker_stream_reconnect_max_seconds: float = Field(default=60, ge=1, le=600)
    broker_stream_reconnect_stable_reset_seconds: int = Field(default=300, ge=30)
    broker_stream_stale_seconds: int = Field(default=120, ge=30)
    broker_stream_watchdog_interval_seconds: int = Field(default=30, ge=5)
    account_event_debounce_seconds: int = Field(default=20, ge=1, le=300)
    account_event_max_debounce_seconds: int = Field(default=60, ge=1, le=900)
    operations_sync_lookback_hours: int = Field(default=24, ge=1, le=720)
    operations_sync_max_pages: int = Field(default=20, ge=1, le=100)
    stream_event_max_processing_attempts: int = Field(default=5, ge=1, le=20)
    stream_event_processing_timeout_seconds: int = Field(default=60, ge=5, le=600)
    stream_event_retention_days: int = Field(default=30, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_telegram_configuration(self) -> "Settings":
        if self.telegram_notifications_enabled and (
            self.telegram_bot_token is None or not self.telegram_chat_id
        ):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required "
                "when notifications are enabled"
            )
        return self

    @model_validator(mode="after")
    def validate_stream_configuration(self) -> "Settings":
        if self.broker_stream_lock_renew_interval_seconds >= self.broker_stream_lock_ttl_seconds:
            raise ValueError("Stream lock renew interval must be lower than lock TTL")
        if self.account_event_debounce_seconds > self.account_event_max_debounce_seconds:
            raise ValueError("Account debounce must not exceed maximum debounce")
        if self.broker_stream_reconnect_initial_seconds > self.broker_stream_reconnect_max_seconds:
            raise ValueError("Reconnect initial delay must not exceed maximum delay")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
