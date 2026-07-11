import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.admin.repository import AdminRepository
from app.admin.schemas import InstrumentReference
from app.admin.service import AdminService
from app.automation.broker import RetryingBrokerProvider
from app.automation.dto import AutomationCycleRequest
from app.automation.factory import create_automation_service
from app.automation.repository import AutomationRepository
from app.automation.retry import RetryPolicy
from app.broker.factory import create_broker_provider
from app.core.config import get_settings
from app.db.session import session_factory
from app.models.enums import AutomationTrigger, StreamEventProcessingStatus
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.factory import create_notifier
from app.streams.processor import process_event, run_reconciliation_job
from app.streams.repository import StreamRepository


async def run_automation_cycle(
    ctx: dict[str, Any],
    correlation_id: str,
    trigger: str,
    actor: str,
    run_id: str | None = None,
) -> dict[str, str]:
    settings = get_settings()
    async with session_factory() as session:
        service = create_automation_service(session, ctx["redis"], settings)
        result = await service.run(
            AutomationCycleRequest(
                trigger=AutomationTrigger(trigger),
                correlation_id=correlation_id,
                actor=actor,
                run_id=UUID(run_id) if run_id else None,
            )
        )
    return {"run_id": str(result.run_id), "status": result.status.value}


async def sync_accounts(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    broker = RetryingBrokerProvider(create_broker_provider(settings), _retry_policy(settings))
    accounts = await broker.get_accounts()
    async with session_factory() as session:
        repository = AutomationRepository(session)
        for account in accounts:
            portfolio = await broker.get_portfolio(account.account_id)
            await repository.save_broker_state(
                account, portfolio, settings.tinvest_target == "sandbox"
            )
    return {"accounts": len(accounts)}


async def sync_instruments(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    broker = RetryingBrokerProvider(create_broker_provider(settings), _retry_policy(settings))
    async with session_factory() as session:
        repository = AdminRepository(session)
        watchlist = await repository.list_watchlist()
        references = [
            InstrumentReference(
                ticker=item.instrument.ticker,
                class_code=item.instrument.class_code,
            )
            for item in watchlist
        ]
        if references:
            await AdminService(repository, broker, settings).sync_instruments(references)
    return {"instruments": len(references)}


async def process_broker_stream_event(ctx: dict[str, Any], event_id: str) -> dict[str, bool]:
    settings = get_settings()
    async with session_factory() as session:
        repository = StreamRepository(session)
        try:
            async with asyncio.timeout(settings.stream_event_processing_timeout_seconds):
                processed = await process_event(
                    repository,
                    ctx["redis"],
                    create_notifier(settings),
                    UUID(event_id),
                    settings.stream_event_max_processing_attempts,
                    settings.account_event_debounce_seconds,
                    settings.account_event_max_debounce_seconds,
                )
        except TimeoutError:
            event = await repository.get_event(UUID(event_id))
            if event is not None:
                await repository.fail_event(
                    event,
                    settings.stream_event_max_processing_attempts,
                    "stream_event_timeout",
                    "Stream event processing timed out",
                )
            processed = False
        if not processed:
            event = await repository.get_event(UUID(event_id))
            if event is not None and event.processing_status is StreamEventProcessingStatus.FAILED:
                await ctx["redis"].enqueue_job(
                    "process_broker_stream_event",
                    event_id,
                    _job_id=f"stream-event:{event_id}:{event.processing_attempts}",
                    _defer_by=timedelta(seconds=min(60, 2**event.processing_attempts)),
                )
    return {"processed": processed}


async def reconcile_account(ctx: dict[str, Any], account_id: str, state_key: str) -> dict[str, Any]:
    return await run_reconciliation_job(ctx, account_id, state_key)


async def cleanup_processed_stream_events(ctx: dict[str, Any]) -> dict[str, int]:
    settings = get_settings()
    before = datetime.now(UTC) - timedelta(days=settings.stream_event_retention_days)
    async with session_factory() as session:
        deleted = await StreamRepository(session).cleanup(before)
    return {"deleted": deleted}


def _retry_policy(settings: Any) -> RetryPolicy:
    return RetryPolicy(
        settings.broker_retry_max_attempts,
        settings.broker_retry_base_delay_seconds,
        settings.broker_retry_max_delay_seconds,
    )


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    threshold = datetime.now(UTC) - timedelta(seconds=settings.stale_run_threshold_seconds)
    async with session_factory() as session:
        recovered = await AutomationRepository(session).recover_stale(threshold)
        stream_repository = StreamRepository(session)
        await stream_repository.startup_recovery()
        pending_event_ids = await stream_repository.pending_event_ids()
    for event_id in pending_event_ids:
        await ctx["redis"].enqueue_job(
            "process_broker_stream_event",
            str(event_id),
            _job_id=f"stream-event-recovery:{event_id}",
        )
    if recovered:
        await create_notifier(settings).send(
            Notification(
                "Stale automation runs recovered",
                f"Восстановлено зависших запусков: {len(recovered)}.",
                NotificationSeverity.WARNING,
            )
        )


class WorkerSettings:
    settings = get_settings()
    functions = [
        run_automation_cycle,
        sync_accounts,
        sync_instruments,
        process_broker_stream_event,
        reconcile_account,
        cleanup_processed_stream_events,
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    health_check_key = "automation:worker:health"
    health_check_interval = 30
    job_timeout = settings.automation_run_timeout_seconds + 30
    max_jobs = 1
    handle_signals = True
