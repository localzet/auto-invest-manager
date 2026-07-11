from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.broker import RetryingBrokerProvider
from app.automation.repository import AutomationRepository
from app.automation.retry import RetryPolicy
from app.broker.factory import create_broker_provider
from app.core.config import Settings
from app.notifications.factory import create_notifier
from app.streams.reconciliation import AccountReconciliationService
from app.streams.repository import StreamRepository


def create_reconciliation_service(
    session: AsyncSession, redis: Redis, settings: Settings
) -> AccountReconciliationService:
    retry = RetryPolicy(
        settings.broker_retry_max_attempts,
        settings.broker_retry_base_delay_seconds,
        settings.broker_retry_max_delay_seconds,
    )
    broker = RetryingBrokerProvider(create_broker_provider(settings), retry)
    return AccountReconciliationService(
        StreamRepository(session),
        AutomationRepository(session),
        broker,
        create_notifier(settings),
        settings.broker_provider,
        settings.tinvest_target,
        settings.operations_sync_lookback_hours,
        settings.operations_sync_max_pages,
        settings.tinvest_target == "sandbox",
    )
