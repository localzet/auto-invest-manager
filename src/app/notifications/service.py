import logging

from app.notifications.dto import Notification
from app.notifications.interface import Notifier

logger = logging.getLogger(__name__)


class NullNotifier:
    async def send(self, notification: Notification) -> None:
        return None


class BestEffortNotifier:
    def __init__(self, delegate: Notifier) -> None:
        self._delegate = delegate

    async def send(self, notification: Notification) -> None:
        try:
            await self._delegate.send(notification)
        except Exception as error:
            logger.warning(
                "Notification delivery failed: %s (%s)",
                notification.title,
                type(error).__name__,
            )
