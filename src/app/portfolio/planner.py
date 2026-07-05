from decimal import ROUND_FLOOR, Decimal

from app.models.enums import AllocationAction
from app.portfolio.dto import (
    OptimizationConstraints,
    OptimizationResult,
    PlannedAllocation,
    RebalanceResult,
)
from app.portfolio.errors import PortfolioOptimizationError


class RebalancePlanner:
    def plan(
        self,
        optimization: OptimizationResult,
        constraints: OptimizationConstraints,
        portfolio_value: Decimal,
        cash_available: Decimal,
    ) -> RebalanceResult:
        if portfolio_value <= 0:
            raise PortfolioOptimizationError("portfolio_value must be positive")
        reserve = portfolio_value * optimization.cash_weight
        spendable_cash = max(Decimal(0), cash_available - reserve)
        allocations: list[PlannedAllocation] = []

        ordered = sorted(
            optimization.targets,
            key=lambda target: (target.asset.priority, target.weight),
            reverse=True,
        )
        for target in ordered:
            asset = target.asset
            current_weight = asset.current_value / portfolio_value
            target_amount = target.weight * portfolio_value
            delta = target_amount - asset.current_value
            relative_delta = abs(delta) / portfolio_value
            action = AllocationAction.HOLD
            lots = 0
            reason = "within rebalance threshold"
            lot_cost = asset.price * asset.lot_size

            if asset.cooldown_active:
                reason = "instrument cooldown is active"
            elif (
                relative_delta >= constraints.rebalance_threshold
                and delta > 0
                and asset.buy_enabled
            ):
                affordable = min(delta, spendable_cash)
                lots = int((affordable / lot_cost).to_integral_value(rounding=ROUND_FLOOR))
                if lots > 0:
                    action = AllocationAction.BUY
                    spendable_cash -= Decimal(lots) * lot_cost
                    reason = "underweight position"
                else:
                    reason = "insufficient cash for minimum lot"
            elif (
                relative_delta >= constraints.rebalance_threshold
                and delta < 0
                and asset.sell_enabled
            ):
                lots = min(
                    asset.current_lots,
                    int((abs(delta) / lot_cost).to_integral_value(rounding=ROUND_FLOOR)),
                )
                if lots > 0:
                    action = AllocationAction.SELL
                    reason = "overweight position"
                else:
                    reason = "delta is below minimum lot"

            allocations.append(
                PlannedAllocation(
                    asset=asset,
                    target_weight=target.weight,
                    current_weight=current_weight,
                    target_amount=target_amount,
                    delta_amount=delta,
                    action=action,
                    lots=lots,
                    reason=reason,
                )
            )
        return RebalanceResult(tuple(allocations), optimization.cash_weight, spendable_cash)
