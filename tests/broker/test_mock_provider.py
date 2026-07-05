from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.broker.dto import CandleInterval
from app.broker.errors import InstrumentNotFoundError
from app.broker.mock import MockBrokerProvider


async def test_mock_provider_returns_deterministic_market_data() -> None:
    provider = MockBrokerProvider()
    from_ = datetime(2026, 1, 1, tzinfo=UTC)

    instrument = await provider.find_instrument("sber", "tqbr")
    candles = await provider.get_candles(
        instrument.instrument_uid,
        from_,
        datetime(2026, 1, 1, 3, tzinfo=UTC),
        CandleInterval.HOUR,
    )
    prices = await provider.get_last_prices((instrument.instrument_uid,))

    assert instrument.lot == 10
    assert [candle.close for candle in candles] == [
        Decimal("312.50"),
        Decimal("313.50"),
        Decimal("314.50"),
    ]
    assert prices[0].price == Decimal("312.50")


async def test_mock_provider_rejects_unknown_instrument() -> None:
    provider = MockBrokerProvider()

    with pytest.raises(InstrumentNotFoundError, match="UNKNOWN/TQBR"):
        await provider.find_instrument("UNKNOWN", "TQBR")


async def test_mock_portfolio_has_consistent_account() -> None:
    provider = MockBrokerProvider()

    accounts = await provider.get_accounts()
    portfolio = await provider.get_portfolio(accounts[0].account_id)

    assert portfolio.account_id == accounts[0].account_id
    assert portfolio.total_amount.amount == Decimal("100000.00")
