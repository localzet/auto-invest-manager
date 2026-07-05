from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.execution.dto import PlannedOrderData, RiskContext
from app.execution.risk import RiskManager
from app.models.enums import OrderDirection, OrderType, TradeMode


def order() -> PlannedOrderData:
    return PlannedOrderData(
        instrument_uid="uid",
        ticker="SBER",
        direction=OrderDirection.BUY,
        lots=1,
        lot_size=10,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("100"),
        reason="test",
        trade_mode=TradeMode.DRY_RUN,
        idempotency_key="key",
    )


def context() -> RiskContext:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return RiskContext(
        kill_switch=False,
        trade_mode=TradeMode.DRY_RUN,
        account_id="account",
        expected_account_id="account",
        in_watchlist=True,
        direction_allowed=True,
        api_trade_available=True,
        order_type_available=True,
        price_time=now - timedelta(seconds=10),
        now=now,
        max_price_age_seconds=60,
        market_price=Decimal("100"),
        max_slippage_percent=Decimal("0.005"),
        cash_available=Decimal("10000"),
        current_position_lots=0,
        current_position_value=Decimal(0),
        portfolio_value=Decimal("100000"),
        max_position_weight=Decimal("0.20"),
        max_trade_amount=Decimal("5000"),
        daily_trades=0,
        max_daily_trades=5,
        cooldown_active=False,
        duplicate_active_order=False,
        idempotency_key_exists=False,
    )


def test_risk_manager_accepts_safe_dry_run_order() -> None:
    decision = RiskManager().evaluate(order(), context())

    assert decision.allowed
    assert decision.reasons == ()


def test_risk_manager_accumulates_safety_failures() -> None:
    unsafe = replace(context(), kill_switch=True)

    decision = RiskManager().evaluate(order(), unsafe)

    assert not decision.allowed
    assert "global kill switch is active" in decision.reasons


def test_risk_manager_rejects_limit_price_outside_slippage() -> None:
    unsafe_order = replace(order(), limit_price=Decimal("110"))

    decision = RiskManager().evaluate(unsafe_order, context())

    assert "limit price exceeds slippage limit" in decision.reasons
