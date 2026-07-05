from collections.abc import Sequence
from decimal import Decimal

from app.portfolio.dto import (
    AssetInput,
    OptimizationConstraints,
    OptimizationResult,
    TargetWeight,
)
from app.portfolio.errors import PortfolioOptimizationError


class PortfolioOptimizer:
    def optimize(
        self,
        assets: Sequence[AssetInput],
        constraints: OptimizationConstraints,
    ) -> OptimizationResult:
        self._validate(assets, constraints)
        investable = Decimal(1) - constraints.min_cash_weight
        weights = {asset.instrument_uid: Decimal(0) for asset in assets}

        manual = [asset for asset in assets if asset.manual_target_weight is not None]
        for asset in manual:
            cap = min(constraints.max_position_weight, asset.max_weight or Decimal(1))
            weights[asset.instrument_uid] = min(asset.manual_target_weight or Decimal(0), cap)

        remaining = investable - sum(weights.values(), Decimal(0))
        candidates = [
            asset
            for asset in assets
            if asset.manual_target_weight is None and asset.buy_enabled and asset.signal_score > 0
        ]
        uncapped = list(candidates)
        while remaining > 0 and uncapped:
            score_sum = sum((asset.signal_score for asset in uncapped), Decimal(0))
            if score_sum <= 0:
                break
            distributed = Decimal(0)
            next_round: list[AssetInput] = []
            for asset in uncapped:
                proposed = remaining * asset.signal_score / score_sum
                cap = min(constraints.max_position_weight, asset.max_weight or Decimal(1))
                capacity = cap - weights[asset.instrument_uid]
                allocated = min(proposed, max(Decimal(0), capacity))
                weights[asset.instrument_uid] += allocated
                distributed += allocated
                if weights[asset.instrument_uid] < cap:
                    next_round.append(asset)
            if distributed <= 0:
                break
            remaining -= distributed
            uncapped = next_round

        total_weight = sum(weights.values(), Decimal(0))
        return OptimizationResult(
            targets=tuple(TargetWeight(asset, weights[asset.instrument_uid]) for asset in assets),
            cash_weight=Decimal(1) - total_weight,
        )

    @staticmethod
    def _validate(assets: Sequence[AssetInput], constraints: OptimizationConstraints) -> None:
        if not 0 <= constraints.min_cash_weight <= 1:
            raise PortfolioOptimizationError("min_cash_weight must be in [0, 1]")
        if not 0 < constraints.max_position_weight <= 1:
            raise PortfolioOptimizationError("max_position_weight must be in (0, 1]")
        if len({asset.instrument_uid for asset in assets}) != len(assets):
            raise PortfolioOptimizationError("instrument_uid values must be unique")
        if any(asset.price <= 0 or asset.lot_size <= 0 for asset in assets):
            raise PortfolioOptimizationError("asset price and lot size must be positive")
        if any(asset.current_value < 0 or asset.current_lots < 0 for asset in assets):
            raise PortfolioOptimizationError("current positions cannot be negative")
        if any(not 0 <= asset.signal_score <= 1 for asset in assets):
            raise PortfolioOptimizationError("signal scores must be in [0, 1]")
        manual_total = sum(
            (asset.manual_target_weight or Decimal(0) for asset in assets), Decimal(0)
        )
        if manual_total > Decimal(1) - constraints.min_cash_weight:
            raise PortfolioOptimizationError("manual targets exceed investable portfolio weight")
