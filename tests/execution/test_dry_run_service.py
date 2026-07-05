from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from app.broker.mock import MockBrokerProvider
from app.core.config import Settings
from app.execution.service import DryRunExecutionService
from app.models.enums import (
    OrderDirection,
    OrderType,
    PlannedOrderStatus,
    TradeMode,
)


async def test_safe_order_creates_virtual_trade() -> None:
    now = datetime(2026, 1, 5, 12, tzinfo=UTC)
    instrument = SimpleNamespace(
        id=UUID(int=2),
        instrument_uid="mock-sber-uid",
        ticker="SBER",
        lot=10,
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
        trade_mode=TradeMode.DRY_RUN,
        idempotency_key="key",
    )
    virtual_trade = SimpleNamespace(id=UUID(int=3))
    repository = SimpleNamespace(
        get_order=AsyncMock(return_value=order),
        get_settings=AsyncMock(
            return_value=SimpleNamespace(kill_switch=False, trade_mode=TradeMode.DRY_RUN)
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
        latest_virtual_trade=AsyncMock(return_value=None),
        count_virtual_trades_since=AsyncMock(return_value=0),
        has_duplicate_order=AsyncMock(return_value=False),
        reject=AsyncMock(),
        simulate=AsyncMock(return_value=virtual_trade),
    )
    service = DryRunExecutionService(
        repository,
        MockBrokerProvider(clock=lambda: now),
        Settings(_env_file=None),
        clock=lambda: now,
    )

    result = await service.execute(order.id)

    assert result is virtual_trade
    repository.simulate.assert_awaited_once_with(order)
    repository.reject.assert_not_awaited()
