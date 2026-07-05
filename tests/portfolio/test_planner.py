from dataclasses import replace
from decimal import Decimal

from app.models.enums import AllocationAction
from app.portfolio.dto import AssetInput, OptimizationConstraints, OptimizationResult, TargetWeight
from app.portfolio.planner import RebalancePlanner

CONSTRAINTS = OptimizationConstraints(
    max_position_weight=Decimal("0.50"),
    min_cash_weight=Decimal("0.10"),
    rebalance_threshold=Decimal("0.03"),
)


def make_asset() -> AssetInput:
    return AssetInput(
        instrument_uid="asset",
        signal_score=Decimal("0.80"),
        current_value=Decimal(0),
        current_lots=0,
        price=Decimal(300),
        lot_size=10,
    )


def test_zero_cash_keeps_recommendation_without_buy_lots() -> None:
    asset = make_asset()
    optimization = OptimizationResult((TargetWeight(asset, Decimal("0.50")),), Decimal("0.50"))

    result = RebalancePlanner().plan(
        optimization, CONSTRAINTS, portfolio_value=Decimal(100_000), cash_available=Decimal(0)
    )

    allocation = result.allocations[0]
    assert allocation.target_weight == Decimal("0.50")
    assert allocation.action is AllocationAction.HOLD
    assert allocation.lots == 0
    assert allocation.reason == "insufficient cash for minimum lot"


def test_buy_plan_uses_whole_lots_and_preserves_cash_reserve() -> None:
    asset = make_asset()
    optimization = OptimizationResult((TargetWeight(asset, Decimal("0.50")),), Decimal("0.50"))

    result = RebalancePlanner().plan(
        optimization, CONSTRAINTS, portfolio_value=Decimal(100_000), cash_available=Decimal(80_000)
    )

    assert result.allocations[0].action is AllocationAction.BUY
    assert result.allocations[0].lots == 10
    assert result.unallocated_cash == Decimal(0)


def test_small_delta_does_not_trigger_rebalance() -> None:
    asset = replace(make_asset(), current_value=Decimal(48_000), current_lots=160)
    optimization = OptimizationResult((TargetWeight(asset, Decimal("0.50")),), Decimal("0.50"))

    result = RebalancePlanner().plan(
        optimization, CONSTRAINTS, portfolio_value=Decimal(100_000), cash_available=Decimal(52_000)
    )

    assert result.allocations[0].action is AllocationAction.HOLD
    assert result.allocations[0].reason == "within rebalance threshold"
