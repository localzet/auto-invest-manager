from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.broker.dto import CandleData, CandleInterval
from app.models.enums import SignalRecommendation
from app.signals.engine import BaselineSignalEngine
from app.signals.errors import SignalCalculationError


def candles(prices: list[Decimal]) -> list[CandleData]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        CandleData(
            instrument_uid="instrument",
            interval=CandleInterval.DAY,
            time=start + timedelta(days=index),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1000,
            is_complete=True,
        )
        for index, price in enumerate(prices)
    ]


def test_flat_market_results_in_hold() -> None:
    result = BaselineSignalEngine().calculate(candles([Decimal("100")] * 20), 0.65)

    assert result.final_score == Decimal("0.500000")
    assert result.recommendation is SignalRecommendation.HOLD


def test_consistent_uptrend_results_in_buy() -> None:
    prices = [Decimal(100 + index * 2) for index in range(20)]

    result = BaselineSignalEngine().calculate(candles(prices), 0.65)

    assert result.final_score >= Decimal("0.65")
    assert result.recommendation is SignalRecommendation.BUY
    assert all(
        Decimal(0) <= score <= Decimal(1)
        for score in (
            result.trend_score,
            result.moving_average_score,
            result.volatility_score,
            result.volume_score,
            result.drawdown_score,
        )
    )


def test_consistent_downtrend_results_in_sell() -> None:
    prices = [Decimal(150 - index * 2) for index in range(20)]

    result = BaselineSignalEngine().calculate(candles(prices), 0.65)

    assert result.final_score <= Decimal("0.35")
    assert result.recommendation is SignalRecommendation.SELL


def test_incomplete_candles_do_not_satisfy_minimum_window() -> None:
    data = candles([Decimal("100")] * 20)
    data[-1] = replace(data[-1], is_complete=False)

    with pytest.raises(SignalCalculationError, match="20 complete candles"):
        BaselineSignalEngine().calculate(data, 0.65)
