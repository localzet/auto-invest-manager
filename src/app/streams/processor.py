from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

from app.models.enums import (
    AccountEventType,
    AutomationTrigger,
    BrokerStreamEventKind,
    ReconciliationReason,
    ReconciliationStatus,
)
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.interface import Notifier
from app.streams.factory import create_reconciliation_service
from app.streams.repository import StreamRepository


async def process_event(
    repository: StreamRepository,
    redis: Any,
    notifier: Notifier,
    event_id: UUID,
    max_attempts: int,
    debounce_seconds: int,
    max_debounce_seconds: int,
) -> bool:
    event = await repository.claim_event(event_id, max_attempts)
    if event is None:
        return False
    try:
        if event.event_kind is BrokerStreamEventKind.SUBSCRIPTION_STATUS:
            await repository.complete_event(event, ignored=True)
            return True
        if event.event_kind is BrokerStreamEventKind.USER_TRADE_EXECUTED:
            await repository.record_trade_signal(event)
        reason = {
            BrokerStreamEventKind.PORTFOLIO_UPDATED: ReconciliationReason.PORTFOLIO_CHANGED,
            BrokerStreamEventKind.POSITIONS_UPDATED: ReconciliationReason.POSITIONS_CHANGED,
            BrokerStreamEventKind.USER_TRADE_EXECUTED: ReconciliationReason.USER_TRADE,
        }.get(event.event_kind)
        if reason is None:
            await repository.complete_event(event, ignored=True)
            return True
        await schedule_debounced_reconciliation(
            redis,
            event.account_id,
            reason,
            debounce_seconds,
            max_debounce_seconds,
        )
        await repository.complete_event(event)
        return True
    except Exception as error:
        safe_message = f"Stream event processing failed ({type(error).__name__})"
        dead = await repository.fail_event(
            event, max_attempts, "stream_event_processing_failed", safe_message
        )
        if dead:
            await notifier.send(
                Notification(
                    "Broker stream event moved to dead letter",
                    f"Event {event.id} requires manual retry.",
                    NotificationSeverity.CRITICAL,
                )
            )
        return False


async def schedule_debounced_reconciliation(
    redis: Any,
    account_id: str,
    reason: ReconciliationReason,
    debounce_seconds: int,
    max_debounce_seconds: int,
) -> str:
    account_hash = sha256(account_id.encode()).hexdigest()[:24]
    state_key = f"account-reconciliation:{account_hash}"
    reasons_key = f"{state_key}:reasons"
    first = datetime.now(UTC).isoformat()
    created = await redis.set(state_key, first, nx=True, ex=max_debounce_seconds + 60)
    await redis.sadd(reasons_key, reason.value)
    await redis.expire(reasons_key, max_debounce_seconds + 60)
    if created:
        await redis.enqueue_job(
            "reconcile_account",
            account_id,
            state_key,
            _job_id=f"reconcile:{account_hash}:{int(datetime.now(UTC).timestamp())}",
            _defer_by=timedelta(seconds=debounce_seconds),
        )
    return state_key


async def run_reconciliation_job(
    ctx: dict[str, Any], account_id: str, state_key: str
) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.db.session import session_factory

    settings = get_settings()
    redis = ctx["redis"]
    raw_reasons = await redis.smembers(f"{state_key}:reasons")
    reasons = {
        ReconciliationReason(item.decode() if isinstance(item, bytes) else str(item))
        for item in raw_reasons
    } or {ReconciliationReason.STREAM_RECONNECTED}
    correlation_id = f"reconciliation:{sha256((account_id + state_key).encode()).hexdigest()}"
    async with session_factory() as session:
        result = await create_reconciliation_service(session, redis, settings).reconcile(
            account_id, reasons, correlation_id
        )
        repository = StreamRepository(session)
        if (
            result.status is ReconciliationStatus.SUCCEEDED
            and result.event_types
            and settings.stream_automation_trigger_enabled
        ):
            trigger = (
                AutomationTrigger.DEPOSIT_DETECTED
                if AccountEventType.DEPOSIT_DETECTED in result.event_types
                else AutomationTrigger.ACCOUNT_CHANGE
            )
            automation_correlation = f"event:{result.reconciliation_id}:{trigger.value}"
            await redis.enqueue_job(
                "run_automation_cycle",
                automation_correlation,
                trigger.value,
                "reconciliation-worker",
                _job_id=f"automation:{automation_correlation}",
            )
            await repository.add_audit(
                "automation.event_trigger.enqueued",
                "reconciliation-worker",
                "Event-driven automation cycle queued",
                {"trigger": trigger.value},
            )
        elif result.event_types:
            await repository.add_audit(
                "automation.event_trigger.skipped",
                "reconciliation-worker",
                "Event-driven automation trigger is disabled",
                {"reason": "stream_automation_trigger_disabled"},
            )
    await redis.delete(state_key, f"{state_key}:reasons")
    return {
        "reconciliation_id": str(result.reconciliation_id),
        "status": result.status.value,
        "events": [item.value for item in result.event_types],
    }
