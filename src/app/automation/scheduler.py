import asyncio
import random
import signal
from datetime import UTC, datetime, timedelta

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.automation.retry import RetryPolicy
from app.automation.service import scheduled_correlation_id
from app.broker.factory import create_broker_provider
from app.core.config import get_settings
from app.db.session import session_factory
from app.models.entities import StrategyProfile


async def run_scheduler() -> None:
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    resolved_account_id = settings.tinvest_account_id
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for exit_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(exit_signal, stop_event.set)
    try:
        while not stop_event.is_set():
            await redis.set("automation:scheduler:heartbeat", datetime.now(UTC).isoformat(), ex=90)
            if settings.automation_scheduler_enabled:
                async with session_factory() as session:
                    strategy = await session.scalar(
                        select(StrategyProfile).where(StrategyProfile.name == "default").limit(1)
                    )
                if resolved_account_id is None:
                    accounts = await RetryPolicy(
                        settings.broker_retry_max_attempts,
                        settings.broker_retry_base_delay_seconds,
                        settings.broker_retry_max_delay_seconds,
                    ).run(create_broker_provider(settings).get_accounts)
                    if len(accounts) != 1:
                        raise ValueError(
                            "TINVEST_ACCOUNT_ID is required when account count is not one"
                        )
                    resolved_account_id = accounts[0].account_id
                account_id = resolved_account_id
                strategy_id = strategy.id if strategy else "default"
                correlation_id = scheduled_correlation_id(
                    account_id,
                    strategy_id,
                    settings.automation_cycle_interval_seconds,
                )
                await redis.enqueue_job(
                    "run_automation_cycle",
                    correlation_id,
                    "SCHEDULED",
                    "scheduler",
                    _job_id=f"automation:{correlation_id}",
                    _defer_by=timedelta(
                        seconds=random.uniform(0, settings.automation_cycle_jitter_seconds)
                    ),
                )
                now_bucket = int(datetime.now(UTC).timestamp())
                account_bucket = now_bucket // settings.account_sync_interval_seconds
                instrument_bucket = now_bucket // settings.instrument_sync_interval_seconds
                await redis.enqueue_job(
                    "sync_accounts",
                    _job_id=f"account-sync:{account_id}:{account_bucket}",
                )
                await redis.enqueue_job(
                    "sync_instruments",
                    _job_id=f"instrument-sync:{instrument_bucket}",
                )
            cleanup_bucket = int(datetime.now(UTC).timestamp()) // 86400
            await redis.enqueue_job(
                "cleanup_processed_stream_events",
                _job_id=f"stream-cleanup:{cleanup_bucket}",
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except TimeoutError:
                pass
    finally:
        await redis.aclose()


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
