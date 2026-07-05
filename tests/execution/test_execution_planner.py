from decimal import Decimal
from uuid import UUID

from app.execution.dto import ExecutionAllocation
from app.execution.planner import ExecutionPlanner
from app.models.enums import OrderDirection, OrderType, TradeMode


def test_planner_builds_deterministic_limit_order() -> None:
    allocation = ExecutionAllocation(
        instrument_uid="uid",
        ticker="SBER",
        direction=OrderDirection.BUY,
        lots=2,
        lot_size=10,
        market_price=Decimal("312.50"),
        reason="underweight",
    )
    planner = ExecutionPlanner()

    first = planner.plan(
        UUID(int=1), [allocation], OrderType.LIMIT, Decimal("0.005"), TradeMode.DRY_RUN
    )[0]
    second = planner.plan(
        UUID(int=1), [allocation], OrderType.LIMIT, Decimal("0.005"), TradeMode.DRY_RUN
    )[0]

    assert first.limit_price == Decimal("314.07")
    assert first.idempotency_key == second.idempotency_key
