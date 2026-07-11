import json
from hashlib import sha256
from typing import Any

from app.broker.dto import BrokerStreamEvent

SENSITIVE_KEYS = {"authorization", "api_key", "token", "telegram_bot_token", "metadata"}


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list | tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str) and any(marker in value.lower() for marker in ("bearer ", "token=")):
        return "[redacted]"
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        sanitize_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def event_dedupe_key(event: BrokerStreamEvent) -> str:
    identity = {
        "provider": event.provider,
        "target": event.target,
        "stream_type": event.stream_type,
        "account_id": event.account_id,
        "event_kind": event.event_kind,
        "broker_event_time": (
            event.broker_event_time.isoformat() if event.broker_event_time else None
        ),
        "source_event_id": event.source_event_id,
        "payload": sanitize_payload(event.payload),
    }
    return sha256(canonical_json(identity).encode()).hexdigest()


def fingerprint(*parts: object) -> str:
    return sha256(":".join(str(part) for part in parts).encode()).hexdigest()


def should_persist_event(event: BrokerStreamEvent) -> bool:
    return event.event_kind != "PING"
