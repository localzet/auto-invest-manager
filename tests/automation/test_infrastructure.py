from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.automation.broker import RetryingBrokerProvider
from app.automation.lock import RedisCycleLock
from app.automation.repository import AutomationRepository
from app.automation.retry import RetryPolicy
from app.automation.schemas import AutomationStatusResponse
from app.automation.service import scheduled_correlation_id
from app.broker.errors import BrokerTemporaryError
from app.core.config import Settings
from app.models.enums import AutomationRunStatus, TradeMode


async def test_retryable_read_is_retried() -> None:
    operation = AsyncMock(side_effect=[BrokerTemporaryError("temporary"), "success"])

    result = await RetryPolicy(2, 0.001, 0.001, jitter=False).run(operation)

    assert result == "success"
    assert operation.await_count == 2


async def test_non_retryable_error_is_not_retried() -> None:
    operation = AsyncMock(side_effect=ValueError("invalid"))

    with pytest.raises(ValueError):
        await RetryPolicy(3, 0.001, 0.001, jitter=False).run(operation)

    assert operation.await_count == 1


async def test_lock_uses_atomic_owner_checked_release() -> None:
    redis = SimpleRedis()
    lock = RedisCycleLock(redis, 120)

    lease = await lock.acquire("account")
    assert lease is not None
    released = await lock.release(lease)

    assert released is True
    assert redis.eval_args[3] == lease.owner_token


async def test_lock_is_not_released_by_different_owner() -> None:
    redis = SimpleRedis()
    lock = RedisCycleLock(redis, 120)
    lease = await lock.acquire("account")
    assert lease is not None
    redis.owner = "other-owner"

    released = await lock.release(lease)

    assert released is False


def test_scheduled_bucket_is_stable() -> None:
    now = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)

    first = scheduled_correlation_id("account", "strategy", 900, now)
    second = scheduled_correlation_id("account", "strategy", 900, now)

    assert first == second


def test_scheduler_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).automation_scheduler_enabled is False


def test_cycle_interval_below_minimum_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, automation_cycle_interval_seconds=59)


async def test_stale_heartbeat_recovery_marks_run_failed() -> None:
    run = SimpleNamespace(id="run-id")
    scalars = AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=[run])))
    repository = AutomationRepository(SimpleNamespace(scalars=scalars))
    repository.finish = AsyncMock()
    repository.add_audit = AsyncMock()

    recovered = await repository.recover_stale(datetime.now(UTC))

    assert recovered == [run]
    assert repository.finish.await_args.args[1] is AutomationRunStatus.FAILED
    assert repository.finish.await_args.kwargs["error_code"] == "stale_worker_run"


def test_worker_status_schema_does_not_expose_secrets() -> None:
    payload = AutomationStatusResponse(
        scheduler_enabled=False,
        trade_mode=TradeMode.OFF,
        kill_switch=True,
        worker_status="ok",
        scheduler_status="ok",
        running_runs=0,
        last_run=None,
    ).model_dump()

    assert not {"redis_url", "account_id", "broker_token", "telegram_bot_token"} & payload.keys()


async def test_sandbox_order_is_never_retried_by_read_retry_adapter() -> None:
    delegate = SimpleNamespace(
        post_sandbox_order=AsyncMock(side_effect=BrokerTemporaryError("temporary"))
    )
    provider = RetryingBrokerProvider(delegate, RetryPolicy(3, 0.001, 0.001, jitter=False))

    with pytest.raises(BrokerTemporaryError):
        await provider.post_sandbox_order(SimpleNamespace())

    delegate.post_sandbox_order.assert_awaited_once()


class SimpleRedis:
    def __init__(self) -> None:
        self.owner: str | None = None
        self.eval_args: tuple[object, ...] = ()

    async def set(self, key: str, owner: str, **kwargs: object) -> bool:
        if self.owner is not None:
            return False
        self.owner = owner
        return True

    async def eval(self, *args: object) -> int:
        self.eval_args = args
        requested_owner = str(args[3])
        if requested_owner != self.owner:
            return 0
        self.owner = None
        return 1
