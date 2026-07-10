from app.core.config import Settings
from app.notifications.interface import Notifier
from app.notifications.service import BestEffortNotifier, NullNotifier
from app.notifications.telegram import TelegramNotifier


def create_notifier(settings: Settings) -> Notifier:
    if not settings.telegram_notifications_enabled:
        return NullNotifier()
    if settings.telegram_bot_token is None or settings.telegram_chat_id is None:
        raise ValueError("Telegram notification settings are incomplete")
    return BestEffortNotifier(
        TelegramNotifier(
            settings.telegram_bot_token.get_secret_value(),
            settings.telegram_chat_id,
            settings.telegram_timeout_seconds,
        )
    )
