from typing import Any

import httpx

from app.notifications.dto import Notification


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._transport = transport

    async def send(self, notification: Notification) -> None:
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": f"[{notification.severity.value}] {notification.title}\n{notification.message}",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            response = await client.post(self._url, json=payload)
            response.raise_for_status()
