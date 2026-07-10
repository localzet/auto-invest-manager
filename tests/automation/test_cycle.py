import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.automation.dto import AutomationCycleRequest
from app.automation.retry import RetryPolicy
from app.automation.service import AutomationCycleService
from app.models.enums import (
    AllocationAction,
    AutomationRunStatus,
    AutomationTrigger,
    PlannedOrderStatus,
    TradeMode,
)
from app.notifications.service import BestEffortNotifier


class FakeRepository:
    def __init__(self, mode: TradeMode, *, kill_switch: bool = False) -> None:
        self.settings = SimpleNamespace(trade_mode=mode, kill_switch=kill_switch)
        self.run = SimpleNamespace(
            id=UUID(int=1),
            status=AutomationRunStatus.PENDING,
            error_code=None,
            run_metadata={},
        )
        self.steps: list[str] = []
        self.audits: list[str] = []
        self.created = True

    async def get_settings(self) -> object:
        return self.settings

    async def create(self, *args: object) -> tuple[object, bool]:
        return self.run, self.created

    async def get(self, run_id: UUID) -> object:
        return self.run

    async def update_step(self, run: object, step: object, **values: object) -> None:
        self.steps.append(step.value)
        for key, value in values.items():
            setattr(run, key, value)

    async def mark_running(self, run: object, account_id: str) -> None:
        run.status = AutomationRunStatus.RUNNING
        run.account_id = account_id

    async def save_broker_state(self, *args: object) -> None:
        return None

    async def finish(
        self, run: object, status: AutomationRunStatus, actor: str, **values: object
    ) -> None:
        run.status = status
        run.error_code = values.get("error_code")
        run.error_message = values.get("error_message")
        run.run_metadata.update(values.get("metadata") or {})

    async def add_audit(
        self, event_type: str, actor: str, message: str, context: dict[str, object]
    ) -> None:
        self.audits.append(event_type)


class FakeLock:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.released = False

    async def acquire(self, account_id: str) -> object | None:
        return SimpleNamespace() if self.acquired else None

    async def release(self, lease: object) -> bool:
        self.released = True
        return True


def build_service(
    mode: TradeMode,
    *,
    kill_switch: bool = False,
    lock: FakeLock | None = None,
    broker: object | None = None,
    notifier: object | None = None,
) -> tuple[AutomationCycleService, FakeRepository, SimpleNamespace]:
    repository = FakeRepository(mode, kill_switch=kill_switch)
    broker = broker or SimpleNamespace(
        get_accounts=AsyncMock(return_value=(SimpleNamespace(account_id="mock-account"),)),
        get_portfolio=AsyncMock(return_value=SimpleNamespace()),
        get_trading_status=AsyncMock(
            return_value=SimpleNamespace(api_trade_available=True, limit_order_available=True)
        ),
    )
    signal_service = SimpleNamespace(run=AsyncMock(return_value=[SimpleNamespace()]))
    plan = SimpleNamespace(id=UUID(int=2), allocations=[])
    rebalance_service = SimpleNamespace(create_plan=AsyncMock(return_value=plan))
    order_status = (
        PlannedOrderStatus.WAITING_CONFIRMATION
        if mode is TradeMode.REAL_MANUAL_CONFIRM
        else PlannedOrderStatus.PLANNED
    )
    order = SimpleNamespace(id=UUID(int=3), status=order_status)
    execution_service = SimpleNamespace(
        plan_orders=AsyncMock(return_value=[order]),
        execute=AsyncMock(),
        execute_sandbox=AsyncMock(),
    )
    dependencies = SimpleNamespace(
        broker=broker,
        signals=signal_service,
        rebalance=rebalance_service,
        execution=execution_service,
    )
    service = AutomationCycleService(
        repository,
        broker,
        signal_service,
        rebalance_service,
        execution_service,
        lock or FakeLock(),
        RetryPolicy(max_attempts=1, jitter=False),
        notifier or SimpleNamespace(send=AsyncMock()),
        2,
    )
    return service, repository, dependencies


def request() -> AutomationCycleRequest:
    return AutomationCycleRequest(AutomationTrigger.MANUAL, "manual:test", "admin")


async def test_off_skips_without_broker_calls() -> None:
    broker = SimpleNamespace(get_accounts=AsyncMock())
    service, _, _ = build_service(TradeMode.OFF, broker=broker)

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SKIPPED
    broker.get_accounts.assert_not_awaited()


async def test_kill_switch_blocks_before_broker_calls() -> None:
    broker = SimpleNamespace(get_accounts=AsyncMock())
    service, repository, _ = build_service(TradeMode.DRY_RUN, kill_switch=True, broker=broker)

    result = await service.run(request())

    assert result.reason == "kill_switch_enabled"
    assert "automation.safety.rejected" in repository.audits
    broker.get_accounts.assert_not_awaited()


async def test_signal_only_never_calls_planner_or_executor() -> None:
    service, _, dependencies = build_service(TradeMode.SIGNAL_ONLY)

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SUCCEEDED
    dependencies.signals.run.assert_awaited_once()
    dependencies.rebalance.create_plan.assert_not_awaited()
    dependencies.execution.plan_orders.assert_not_awaited()


async def test_dry_run_calls_only_virtual_executor() -> None:
    service, repository, dependencies = build_service(TradeMode.DRY_RUN)

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SUCCEEDED
    dependencies.execution.execute.assert_awaited_once()
    dependencies.execution.execute_sandbox.assert_not_awaited()
    assert repository.run.virtual_trades_count == 1


async def test_sandbox_calls_only_sandbox_executor() -> None:
    service, repository, dependencies = build_service(TradeMode.SANDBOX)

    await service.run(request())

    dependencies.execution.execute_sandbox.assert_awaited_once()
    dependencies.execution.execute.assert_not_awaited()
    assert repository.run.executed_orders_count == 1


async def test_manual_confirmation_does_not_execute() -> None:
    service, _, dependencies = build_service(TradeMode.REAL_MANUAL_CONFIRM)

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SUCCEEDED
    dependencies.execution.execute.assert_not_awaited()
    dependencies.execution.execute_sandbox.assert_not_awaited()


async def test_parallel_cycle_is_skipped_without_waiting() -> None:
    service, repository, dependencies = build_service(
        TradeMode.DRY_RUN, lock=FakeLock(acquired=False)
    )

    result = await service.run(request())

    assert result.reason == "cycle_already_running"
    assert "automation.lock.rejected" in repository.audits
    dependencies.signals.run.assert_not_awaited()


async def test_lock_is_released_after_success() -> None:
    lock = FakeLock()
    service, _, _ = build_service(TradeMode.DRY_RUN, lock=lock)

    await service.run(request())

    assert lock.released is True


async def test_duplicate_correlation_does_not_execute() -> None:
    service, repository, dependencies = build_service(TradeMode.DRY_RUN)
    repository.created = False

    result = await service.run(request())

    assert result.reason == "duplicate_correlation_id"
    dependencies.signals.run.assert_not_awaited()


async def test_market_closed_preserves_analysis_and_skips_orders() -> None:
    service, repository, dependencies = build_service(TradeMode.DRY_RUN)
    dependencies.rebalance.create_plan.return_value.allocations = [
        SimpleNamespace(
            action=AllocationAction.BUY,
            recommended_lots=1,
            instrument=SimpleNamespace(instrument_uid="uid"),
        )
    ]
    dependencies.broker.get_trading_status.return_value = SimpleNamespace(
        api_trade_available=False, limit_order_available=False
    )

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SUCCEEDED
    dependencies.signals.run.assert_awaited_once()
    dependencies.execution.plan_orders.assert_not_awaited()
    assert repository.run.run_metadata["execution_skipped"] == "market_closed"


async def test_timeout_marks_run_failed() -> None:
    async def blocked() -> tuple[object, ...]:
        await asyncio.sleep(1)
        return ()

    broker = SimpleNamespace(get_accounts=blocked)
    service, repository, _ = build_service(TradeMode.DRY_RUN, broker=broker)
    service._timeout_seconds = 0.01

    result = await service.run(request())

    assert result.status is AutomationRunStatus.FAILED
    assert repository.run.error_code == "run_timeout"


async def test_notifier_failure_does_not_break_cycle() -> None:
    delegate = AsyncMock()
    delegate.send.side_effect = RuntimeError("unavailable")
    service, _, _ = build_service(TradeMode.DRY_RUN, notifier=BestEffortNotifier(delegate))

    result = await service.run(request())

    assert result.status is AutomationRunStatus.SUCCEEDED


async def test_failed_error_message_does_not_contain_exception_secret() -> None:
    broker = SimpleNamespace(get_accounts=AsyncMock(side_effect=ValueError("secret-token")))
    service, repository, _ = build_service(TradeMode.DRY_RUN, broker=broker)

    await service.run(request())

    assert "secret-token" not in repository.run.error_message


@pytest.mark.parametrize("mode", [TradeMode.DRY_RUN, TradeMode.SANDBOX])
async def test_execution_modes_record_audit(mode: TradeMode) -> None:
    service, repository, _ = build_service(mode)

    await service.run(request())

    assert "automation.orders.planned" in repository.audits
    assert "automation.execution.completed" in repository.audits
