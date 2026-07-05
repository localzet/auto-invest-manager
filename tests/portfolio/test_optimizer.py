from dataclasses import replace
from decimal import Decimal

from app.portfolio.dto import AssetInput, OptimizationConstraints
from app.portfolio.optimizer import PortfolioOptimizer


def asset(uid: str, score: str) -> AssetInput:
    return AssetInput(
        instrument_uid=uid,
        signal_score=Decimal(score),
        current_value=Decimal(0),
        current_lots=0,
        price=Decimal(100),
        lot_size=1,
    )


def constraints() -> OptimizationConstraints:
    return OptimizationConstraints(
        max_position_weight=Decimal("0.40"),
        min_cash_weight=Decimal("0.20"),
        rebalance_threshold=Decimal("0.03"),
    )


def test_optimizer_respects_position_and_cash_limits() -> None:
    result = PortfolioOptimizer().optimize(
        [asset("strong", "0.8"), asset("weak", "0.2")], constraints()
    )

    weights = {target.asset.instrument_uid: target.weight for target in result.targets}
    assert weights == {"strong": Decimal("0.40"), "weak": Decimal("0.40")}
    assert result.cash_weight == Decimal("0.20")


def test_manual_target_is_preserved_and_capped() -> None:
    manual = replace(asset("manual", "0.1"), manual_target_weight=Decimal("0.30"))

    result = PortfolioOptimizer().optimize([manual, asset("auto", "0.9")], constraints())

    weights = {target.asset.instrument_uid: target.weight for target in result.targets}
    assert weights["manual"] == Decimal("0.30")
    assert weights["auto"] == Decimal("0.40")
    assert result.cash_weight == Decimal("0.30")
