from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.broker.dto import (
    BrokerAccountData,
    BrokerCapabilities,
    BrokerOperation,
    BrokerStreamEvent,
    CandleData,
    CandleInterval,
    InstrumentData,
    LastPriceData,
    MoneyData,
    OperationsCursorPage,
    OperationsCursorRequest,
    PortfolioData,
    PositionData,
    SandboxOrderRequest,
    SandboxOrderResult,
    TradingStatusData,
)
from app.broker.errors import InstrumentNotFoundError

MOCK_NOW = datetime(2026, 1, 5, 12, tzinfo=UTC)


class MockBrokerProvider:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
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
        self._stream_events: dict[str, list[BrokerStreamEvent]] = {
            "PORTFOLIO": [],
            "POSITIONS": [],
            "TRADES": [],
        }
        self._operations: list[BrokerOperation] = []

    @property
    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(True, True, True, True)

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
            captured_at=self._clock(),
        )

    async def get_positions(self, account_id: str) -> tuple[PositionData, ...]:
        return (await self.get_portfolio(account_id)).positions

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
            LastPriceData(instrument_uid=uid, price=self._prices[uid], time=self._clock())
            for uid in instrument_uids
        )

    async def get_trading_status(self, instrument_uid: str) -> TradingStatusData:
        if instrument_uid not in self._prices:
            raise InstrumentNotFoundError(f"Instrument {instrument_uid} not found")
        return TradingStatusData(instrument_uid, True, True, True)

    async def post_sandbox_order(self, request: SandboxOrderRequest) -> SandboxOrderResult:
        raise RuntimeError("Mock provider cannot place sandbox broker orders")

    def queue_stream_event(self, event: BrokerStreamEvent) -> None:
        self._stream_events[event.stream_type].append(event)

    def set_operations(self, operations: Sequence[BrokerOperation]) -> None:
        self._operations = list(operations)

    async def _stream(
        self, stream_type: str, account_ids: Sequence[str]
    ) -> AsyncIterator[BrokerStreamEvent]:
        events = tuple(self._stream_events[stream_type])
        if not events and account_ids:
            now = self._clock()
            yield BrokerStreamEvent(
                "mock",
                "sandbox",
                stream_type,
                "",
                now,
                now,
                "PING",
                None,
                {},
            )
            yield BrokerStreamEvent(
                "mock",
                "sandbox",
                stream_type,
                account_ids[0],
                now,
                now,
                "SUBSCRIPTION_STATUS",
                f"mock-{stream_type.lower()}-subscription",
                {"status": "SUBSCRIPTION_STATUS_SUCCESS"},
            )
            if stream_type in {"PORTFOLIO", "POSITIONS"}:
                yield BrokerStreamEvent(
                    "mock",
                    "sandbox",
                    stream_type,
                    account_ids[0],
                    now,
                    now,
                    f"{stream_type}_UPDATED",
                    f"mock-{stream_type.lower()}-update",
                    {"cash": "68750.00", "currency": "rub"},
                )
        for event in events:
            yield event

    def stream_portfolio(self, account_ids: Sequence[str]) -> AsyncIterator[BrokerStreamEvent]:
        return self._stream("PORTFOLIO", account_ids)

    def stream_positions(self, account_ids: Sequence[str]) -> AsyncIterator[BrokerStreamEvent]:
        return self._stream("POSITIONS", account_ids)

    def stream_user_trades(self, account_ids: Sequence[str]) -> AsyncIterator[BrokerStreamEvent]:
        return self._stream("TRADES", account_ids)

    async def get_operations_page(self, request: OperationsCursorRequest) -> OperationsCursorPage:
        start = int(request.cursor or 0)
        items = tuple(self._operations[start : start + request.limit])
        next_index = start + len(items)
        has_next = next_index < len(self._operations)
        return OperationsCursorPage(
            items=items,
            next_cursor=str(next_index) if has_next else None,
            has_next=has_next,
        )
