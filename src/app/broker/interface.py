from datetime import datetime
from typing import Protocol

from app.broker.dto import (
    BrokerAccountData,
    CandleData,
    CandleInterval,
    InstrumentData,
    LastPriceData,
    PortfolioData,
    SandboxOrderRequest,
    SandboxOrderResult,
    TradingStatusData,
)


class BrokerProvider(Protocol):
    async def get_accounts(self) -> tuple[BrokerAccountData, ...]: ...

    async def get_portfolio(self, account_id: str) -> PortfolioData: ...

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
