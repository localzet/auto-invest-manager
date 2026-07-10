from unittest.mock import AsyncMock

import httpx
from pytest import LogCaptureFixture

from app.core.config import Settings
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.factory import create_notifier
from app.notifications.service import BestEffortNotifier, NullNotifier
from app.notifications.telegram import TelegramNotifier


async def test_telegram_notifier_posts_expected_payload() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode()
        return httpx.Response(200, json={"ok": True})

    notifier = TelegramNotifier(
        "secret-token",
        "123456",
        transport=httpx.MockTransport(handler),
    )

    await notifier.send(
        Notification(
            title="Risk alert",
            message="Order rejected",
            severity=NotificationSeverity.WARNING,
        )
    )

    assert captured["url"] == "https://api.telegram.org/botsecret-token/sendMessage"
    assert '"chat_id":"123456"' in str(captured["payload"])
    assert "[WARNING] Risk alert\\nOrder rejected" in str(captured["payload"])


async def test_best_effort_notifier_does_not_log_sensitive_error(
    caplog: LogCaptureFixture,
) -> None:
    delegate = AsyncMock()
    delegate.send.side_effect = httpx.ConnectError("secret-token must not be logged")
    notifier = BestEffortNotifier(delegate)

    await notifier.send(Notification(title="Test", message="Message"))

    delegate.send.assert_awaited_once()
    assert "ConnectError" in str(caplog.text)
    assert "secret-token" not in str(caplog.text)


def test_factory_uses_null_notifier_by_default() -> None:
    notifier = create_notifier(Settings(_env_file=None))

    assert isinstance(notifier, NullNotifier)
