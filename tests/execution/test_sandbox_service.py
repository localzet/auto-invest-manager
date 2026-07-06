from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from app.broker.dto import SandboxOrderResult
from app.broker.mock import MockBrokerProvider
from app.core.config import Settings
from app.execution.service import ExecutionService
from app.models.enums import OrderDirection, OrderType, PlannedOrderStatus, TradeMode


class FakeSandboxProvider(MockBrokerProvider):
    async def post_sandbox_order(self, request: object) -> SandboxOrderResult:
        return SandboxOrderResult(
            broker_order_id="sandbox-order",
            broker_status="EXECUTION_REPORT_STATUS_NEW",
            lots_requested=1,
            lots_executed=0,
            execution_price=Decimal(0),
            total_amount=Decimal(0),
        )


async def test_sandbox_order_passes_final_risk_check_and_is_persisted() -> None:
    now = datetime(2026, 1, 5, 12, tzinfo=UTC)
    instrument = SimpleNamespace(
        id=UUID(int=2), instrument_uid="mock-sber-uid", ticker="SBER", lot=10
    )
    order = SimpleNamespace(
        id=UUID(int=1),
        virtual_trade=None,
        status=PlannedOrderStatus.PLANNED,
        instrument=instrument,
        instrument_id=instrument.id,
        account_id="mock-account",
        direction=OrderDirection.BUY,
        lots=1,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("312.50"),
        reason="underweight",
        trade_mode=TradeMode.SANDBOX,
        idempotency_key="sandbox-key",
    )
    execution = SimpleNamespace(id=UUID(int=3))
    repository = SimpleNamespace(
        get_order=AsyncMock(return_value=order),
        get_execution_order=AsyncMock(return_value=None),
        get_settings=AsyncMock(
            return_value=SimpleNamespace(kill_switch=False, trade_mode=TradeMode.SANDBOX)
        ),
        get_risk_profile=AsyncMock(
            return_value=SimpleNamespace(
                max_position_weight=Decimal("0.50"),
                max_trade_amount=Decimal("5000"),
                max_slippage_percent=Decimal("0.01"),
                max_daily_trades=5,
                trade_cooldown_seconds=3600,
            )
        ),
        get_watchlist_item=AsyncMock(
            return_value=SimpleNamespace(buy_enabled=True, sell_enabled=True)
        ),
        latest_trade_time=AsyncMock(return_value=None),
        count_trades_since=AsyncMock(return_value=0),
        has_duplicate_order=AsyncMock(return_value=False),
        reject=AsyncMock(),
        save_sandbox_execution=AsyncMock(return_value=execution),
    )
    provider = FakeSandboxProvider(clock=lambda: now)
    service = ExecutionService(
        repository,
        provider,
        Settings(
            _env_file=None,
            broker_provider="tinvest",
            tinvest_target="sandbox",
        ),
        clock=lambda: now,
    )

    result = await service.execute_sandbox(order.id)

    assert result is execution
    repository.save_sandbox_execution.assert_awaited_once()
    repository.reject.assert_not_awaited()
