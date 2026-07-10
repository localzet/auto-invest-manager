from datetime import datetime

from app.automation.retry import RetryPolicy
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
from app.broker.interface import BrokerProvider


class RetryingBrokerProvider:
    def __init__(self, delegate: BrokerProvider, retry_policy: RetryPolicy) -> None:
        self._delegate = delegate
        self._retry = retry_policy

    async def get_accounts(self) -> tuple[BrokerAccountData, ...]:
        return await self._retry.run(self._delegate.get_accounts)

    async def get_portfolio(self, account_id: str) -> PortfolioData:
        return await self._retry.run(lambda: self._delegate.get_portfolio(account_id))

    async def find_instrument(self, ticker: str, class_code: str) -> InstrumentData:
        return await self._retry.run(lambda: self._delegate.find_instrument(ticker, class_code))

    async def get_candles(
        self,
        instrument_uid: str,
        from_: datetime,
        to: datetime,
        interval: CandleInterval,
    ) -> tuple[CandleData, ...]:
        return await self._retry.run(
            lambda: self._delegate.get_candles(instrument_uid, from_, to, interval)
        )

    async def get_last_prices(self, instrument_uids: tuple[str, ...]) -> tuple[LastPriceData, ...]:
        return await self._retry.run(lambda: self._delegate.get_last_prices(instrument_uids))

    async def get_trading_status(self, instrument_uid: str) -> TradingStatusData:
        return await self._retry.run(lambda: self._delegate.get_trading_status(instrument_uid))

    async def post_sandbox_order(self, request: SandboxOrderRequest) -> SandboxOrderResult:
        return await self._delegate.post_sandbox_order(request)
