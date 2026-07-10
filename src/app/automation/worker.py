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
from app.models.enums import AutomationTrigger
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.factory import create_notifier


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
    functions = [run_automation_cycle, sync_accounts, sync_instruments]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    health_check_key = "automation:worker:health"
    health_check_interval = 30
    job_timeout = settings.automation_run_timeout_seconds + 30
    max_jobs = 1
    handle_signals = True
