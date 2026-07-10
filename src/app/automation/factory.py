from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.broker import RetryingBrokerProvider
from app.automation.lock import RedisCycleLock
from app.automation.repository import AutomationRepository
from app.automation.retry import RetryPolicy
from app.automation.service import AutomationCycleService
from app.broker.factory import create_broker_provider
from app.core.config import Settings
from app.execution.repository import ExecutionRepository
from app.execution.service import ExecutionService
from app.notifications.factory import create_notifier
from app.notifications.service import NullNotifier
from app.portfolio.repository import PortfolioRepository
from app.portfolio.service import RebalanceService
from app.signals.repository import SignalRepository
from app.signals.service import SignalAnalysisService


def create_automation_service(
    session: AsyncSession, redis: Redis, settings: Settings
) -> AutomationCycleService:
    broker = create_broker_provider(settings)
    notifier = create_notifier(settings)
    retry_policy = RetryPolicy(
        settings.broker_retry_max_attempts,
        settings.broker_retry_base_delay_seconds,
        settings.broker_retry_max_delay_seconds,
    )
    retrying_broker = RetryingBrokerProvider(broker, retry_policy)
    return AutomationCycleService(
        AutomationRepository(session),
        broker,
        SignalAnalysisService(SignalRepository(session), retrying_broker, notifier=NullNotifier()),
        RebalanceService(
            PortfolioRepository(session),
            retrying_broker,
            settings,
            notifier=NullNotifier(),
        ),
        ExecutionService(
            ExecutionRepository(session),
            retrying_broker,
            settings,
            notifier=NullNotifier(),
        ),
        RedisCycleLock(redis, settings.automation_lock_ttl_seconds),
        retry_policy,
        notifier,
        settings.automation_run_timeout_seconds,
        settings.tinvest_account_id,
    )
