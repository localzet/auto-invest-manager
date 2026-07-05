from app.core.config import Settings


def test_real_trading_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.enable_real_trading is False
    assert settings.global_kill_switch is True
