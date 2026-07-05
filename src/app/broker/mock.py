from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.broker.dto import (
    BrokerAccountData,
    CandleData,
    CandleInterval,
    InstrumentData,
    LastPriceData,
    MoneyData,
    PortfolioData,
    PositionData,
)
from app.broker.errors import InstrumentNotFoundError

MOCK_NOW = datetime(2026, 1, 5, 12, tzinfo=UTC)


class MockBrokerProvider:
    def __init__(self) -> None:
        self._instruments = {
            ("SBER", "TQBR"): InstrumentData(
                instrument_uid="mock-sber-uid",
                figi="BBG004730N88",
                ticker="SBER",
                class_code="TQBR",
                name="Sberbank",
                instrument_type="share",
                currency="rub",
                lot=10,
                api_trade_available=True,
            ),
            ("YDEX", "TQBR"): InstrumentData(
                instrument_uid="mock-ydex-uid",
                figi="TCS00A107T19",
                ticker="YDEX",
                class_code="TQBR",
                name="Yandex",
                instrument_type="share",
                currency="rub",
                lot=1,
                api_trade_available=True,
            ),
        }
        self._prices = {
            "mock-sber-uid": Decimal("312.50"),
            "mock-ydex-uid": Decimal("4210.00"),
        }

    async def get_accounts(self) -> tuple[BrokerAccountData, ...]:
        return (
            BrokerAccountData(
                account_id="mock-account",
                name="Mock brokerage account",
                status="OPEN",
                account_type="BROKER",
                opened_at=datetime(2025, 1, 1, tzinfo=UTC),
            ),
        )

    async def get_portfolio(self, account_id: str) -> PortfolioData:
        if account_id != "mock-account":
            raise ValueError(f"Unknown mock account: {account_id}")
        return PortfolioData(
            account_id=account_id,
            total_amount=MoneyData(Decimal("100000.00"), "rub"),
            expected_yield=Decimal("0.025"),
            positions=(
                PositionData(
                    instrument_uid="mock-sber-uid",
                    figi="BBG004730N88",
                    quantity=Decimal("100"),
                    current_price=MoneyData(self._prices["mock-sber-uid"], "rub"),
                    average_price=MoneyData(Decimal("300.00"), "rub"),
                ),
            ),
            captured_at=MOCK_NOW,
        )

    async def find_instrument(self, ticker: str, class_code: str) -> InstrumentData:
        try:
            return self._instruments[(ticker.upper(), class_code.upper())]
        except KeyError as error:
            raise InstrumentNotFoundError(f"Instrument {ticker}/{class_code} not found") from error

    async def get_candles(
        self,
        instrument_uid: str,
        from_: datetime,
        to: datetime,
        interval: CandleInterval,
    ) -> tuple[CandleData, ...]:
        if instrument_uid not in self._prices:
            raise InstrumentNotFoundError(f"Instrument {instrument_uid} not found")
        step = timedelta(hours=1) if interval is CandleInterval.HOUR else timedelta(days=1)
        candles: list[CandleData] = []
        time = from_
        index = 0
        base = self._prices[instrument_uid]
        while time < to:
            close = base + Decimal(index)
            candles.append(
                CandleData(
                    instrument_uid=instrument_uid,
                    interval=interval,
                    time=time,
                    open=close - Decimal("0.50"),
                    high=close + Decimal("1.00"),
                    low=close - Decimal("1.00"),
                    close=close,
                    volume=1000 + index * 10,
                    is_complete=True,
                )
            )
            time += step
            index += 1
        return tuple(candles)

    async def get_last_prices(self, instrument_uids: tuple[str, ...]) -> tuple[LastPriceData, ...]:
        unknown = set(instrument_uids) - self._prices.keys()
        if unknown:
            raise InstrumentNotFoundError(f"Instruments not found: {sorted(unknown)}")
        return tuple(
            LastPriceData(instrument_uid=uid, price=self._prices[uid], time=MOCK_NOW)
            for uid in instrument_uids
        )
