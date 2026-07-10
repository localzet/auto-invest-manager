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
