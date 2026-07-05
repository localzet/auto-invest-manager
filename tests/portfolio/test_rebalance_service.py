from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.broker.mock import MockBrokerProvider
from app.core.config import Settings
from app.models.enums import AllocationAction
from app.portfolio.service import RebalanceService


async def test_service_builds_lot_aware_plan_from_latest_signal() -> None:
    instrument = SimpleNamespace(
        id="instrument-id",
        instrument_uid="mock-sber-uid",
        ticker="SBER",
        lot=10,
    )
    watchlist_item = SimpleNamespace(
        instrument=instrument,
        min_signal_score=Decimal("0.60"),
        buy_enabled=True,
        sell_enabled=True,
        max_weight=Decimal("0.50"),
        manual_target_weight=None,
        priority=10,
    )
    repository = SimpleNamespace(
        get_risk_profile=AsyncMock(
            return_value=SimpleNamespace(
                max_position_weight=Decimal("0.50"),
                min_cash_weight=Decimal("0.10"),
                rebalance_threshold_percent=Decimal("0.03"),
            )
        ),
        get_watchlist=AsyncMock(return_value=[watchlist_item]),
        get_latest_signal=AsyncMock(return_value=SimpleNamespace(final_score=Decimal("0.80"))),
        save_plan=AsyncMock(return_value="saved-plan"),
    )
    service = RebalanceService(
        repository,
        MockBrokerProvider(),
        Settings(_env_file=None),
    )

    result = await service.create_plan()

    assert result == "saved-plan"
    rebalance = repository.save_plan.await_args.args[3]
    assert rebalance.allocations[0].action is AllocationAction.BUY
    assert rebalance.allocations[0].lots == 6
