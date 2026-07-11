import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_real_trading_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.enable_real_trading is False
    assert settings.global_kill_switch is True
    assert settings.telegram_notifications_enabled is False


def test_enabled_telegram_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None, telegram_notifications_enabled=True)


def test_streams_and_event_automation_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.broker_streams_enabled is False
    assert settings.stream_automation_trigger_enabled is False


@pytest.mark.parametrize(
    "values",
    [
        {"broker_stream_lock_ttl_seconds": 30, "broker_stream_lock_renew_interval_seconds": 30},
        {"account_event_debounce_seconds": 61, "account_event_max_debounce_seconds": 60},
        {"broker_stream_reconnect_initial_seconds": 10, "broker_stream_reconnect_max_seconds": 5},
    ],
)
def test_invalid_stream_configuration_is_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
