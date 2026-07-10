from typing import Protocol

from app.notifications.dto import Notification


class Notifier(Protocol):
    async def send(self, notification: Notification) -> None: ...
