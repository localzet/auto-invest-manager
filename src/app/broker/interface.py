from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Protocol

from app.broker.dto import (
    BrokerAccountData,
    BrokerCapabilities,
    BrokerStreamEvent,
    CandleData,
    CandleInterval,
    InstrumentData,
    LastPriceData,
    OperationsCursorPage,
    OperationsCursorRequest,
    PortfolioData,
    PositionData,
    SandboxOrderRequest,
    SandboxOrderResult,
    TradingStatusData,
)


class BrokerProvider(Protocol):
    @property
    def capabilities(self) -> BrokerCapabilities: ...

    async def get_accounts(self) -> tuple[BrokerAccountData, ...]: ...

    async def get_portfolio(self, account_id: str) -> PortfolioData: ...

    async def get_positions(self, account_id: str) -> tuple[PositionData, ...]: ...

    async def find_instrument(self, ticker: str, class_code: str) -> InstrumentData: ...

    async def get_candles(
        self,
        instrument_uid: str,
        from_: datetime,
        to: datetime,
        interval: CandleInterval,
    ) -> tuple[CandleData, ...]: ...

    async def get_last_prices(
        self, instrument_uids: tuple[str, ...]
    ) -> tuple[LastPriceData, ...]: ...

    async def get_trading_status(self, instrument_uid: str) -> TradingStatusData: ...

    async def post_sandbox_order(self, request: SandboxOrderRequest) -> SandboxOrderResult: ...

    def stream_portfolio(self, account_ids: Sequence[str]) -> AsyncIterator[BrokerStreamEvent]: ...

    def stream_positions(self, account_ids: Sequence[str]) -> AsyncIterator[BrokerStreamEvent]: ...

    def stream_user_trades(
        self, account_ids: Sequence[str]
    ) -> AsyncIterator[BrokerStreamEvent]: ...

    async def get_operations_page(
        self, request: OperationsCursorRequest
    ) -> OperationsCursorPage: ...
