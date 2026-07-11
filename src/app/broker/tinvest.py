from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from importlib.util import find_spec
from typing import Any

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
from app.broker.errors import BrokerConfigurationError, InstrumentNotFoundError

ClientFactory = Callable[[str, str], AbstractAsyncContextManager[Any]]


def _decimal(value: Any) -> Decimal:
    return Decimal(value.units) + Decimal(value.nano) / Decimal(1_000_000_000)


def _enum_name(value: Any) -> str:
    return getattr(value, "name", str(value))


@asynccontextmanager
async def _sdk_client(token: str, target: str) -> AsyncIterator[Any]:
    from tinkoff.invest import AsyncClient

    async with AsyncClient(token, target=target) as client:
        yield client


class TInvestClient:
    def __init__(
        self,
        token: str,
        target: str,
        client_factory: ClientFactory = _sdk_client,
    ) -> None:
        if not token:
            raise BrokerConfigurationError("T-Invest token is required")
        if client_factory is _sdk_client and find_spec("tinkoff.invest") is None:
            raise BrokerConfigurationError(
                "T-Invest SDK is not installed; install the project with the tinvest extra"
            )
        self._token = token
        self._target = target
        self._client_factory = client_factory

    @property
    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(True, True, True, True)

    async def get_accounts(self) -> tuple[BrokerAccountData, ...]:
        async with self._client_factory(self._token, self._target) as client:
            response = await client.users.get_accounts()
        return tuple(
            BrokerAccountData(
                account_id=item.id,
                name=item.name,
                status=_enum_name(item.status),
                account_type=_enum_name(item.type),
                opened_at=item.opened_date or None,
            )
            for item in response.accounts
        )

    async def get_portfolio(self, account_id: str) -> PortfolioData:
        async with self._client_factory(self._token, self._target) as client:
            response = await client.operations.get_portfolio(account_id=account_id)
        positions = tuple(
            PositionData(
                instrument_uid=item.instrument_uid,
                figi=item.figi,
                quantity=_decimal(item.quantity),
                current_price=MoneyData(_decimal(item.current_price), item.current_price.currency),
                average_price=(
                    MoneyData(
                        _decimal(item.average_position_price), item.average_position_price.currency
                    )
                    if item.average_position_price
                    else None
                ),
            )
            for item in response.positions
        )
        return PortfolioData(
            account_id=account_id,
            total_amount=MoneyData(
                _decimal(response.total_amount_portfolio),
                response.total_amount_portfolio.currency,
            ),
            expected_yield=_decimal(response.expected_yield),
            positions=positions,
            captured_at=datetime.now(UTC),
        )

    async def get_positions(self, account_id: str) -> tuple[PositionData, ...]:
        async with self._client_factory(self._token, self._target) as client:
            response = await client.operations.get_positions(account_id=account_id)
        return tuple(
            PositionData(
                instrument_uid=item.instrument_uid,
                figi=item.figi,
                quantity=Decimal(item.balance),
                current_price=MoneyData(Decimal(0), ""),
                average_price=None,
            )
            for item in response.securities
        )

    async def find_instrument(self, ticker: str, class_code: str) -> InstrumentData:
        async with self._client_factory(self._token, self._target) as client:
            search = await client.instruments.find_instrument(query=ticker)
            matches = [
                item
                for item in search.instruments
                if item.ticker.upper() == ticker.upper()
                and item.class_code.upper() == class_code.upper()
            ]
            if len(matches) != 1:
                raise InstrumentNotFoundError(
                    f"Expected one instrument for {ticker}/{class_code}, found {len(matches)}"
                )
            from tinkoff.invest import InstrumentIdType

            response = await client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                id=matches[0].uid,
            )
        item = response.instrument
        return InstrumentData(
            instrument_uid=item.uid,
            figi=item.figi,
            ticker=item.ticker,
            class_code=item.class_code,
            name=item.name,
            instrument_type=_enum_name(item.instrument_kind).lower(),
            currency=item.currency,
            lot=item.lot,
            api_trade_available=item.api_trade_available_flag,
        )

    async def get_candles(
        self,
        instrument_uid: str,
        from_: datetime,
        to: datetime,
        interval: CandleInterval,
    ) -> tuple[CandleData, ...]:
        from tinkoff.invest import CandleInterval as SdkCandleInterval

        sdk_interval = {
            CandleInterval.HOUR: SdkCandleInterval.CANDLE_INTERVAL_HOUR,
            CandleInterval.DAY: SdkCandleInterval.CANDLE_INTERVAL_DAY,
        }[interval]
        async with self._client_factory(self._token, self._target) as client:
            response = await client.market_data.get_candles(
                instrument_id=instrument_uid,
                from_=from_,
                to=to,
                interval=sdk_interval,
            )
        return tuple(
            CandleData(
                instrument_uid=instrument_uid,
                interval=interval,
                time=item.time,
                open=_decimal(item.open),
                high=_decimal(item.high),
                low=_decimal(item.low),
                close=_decimal(item.close),
                volume=item.volume,
                is_complete=item.is_complete,
            )
            for item in response.candles
        )

    async def get_last_prices(self, instrument_uids: tuple[str, ...]) -> tuple[LastPriceData, ...]:
        if not instrument_uids:
            return ()
        async with self._client_factory(self._token, self._target) as client:
            response = await client.market_data.get_last_prices(instrument_id=list(instrument_uids))
        return tuple(
            LastPriceData(
                instrument_uid=item.instrument_uid,
                price=_decimal(item.price),
                time=item.time,
            )
            for item in response.last_prices
        )

    async def get_trading_status(self, instrument_uid: str) -> TradingStatusData:
        async with self._client_factory(self._token, self._target) as client:
            item = await client.market_data.get_trading_status(instrument_id=instrument_uid)
        return TradingStatusData(
            instrument_uid=instrument_uid,
            api_trade_available=item.api_trade_available_flag,
            market_order_available=item.market_order_available_flag,
            limit_order_available=item.limit_order_available_flag,
        )

    async def post_sandbox_order(self, request: SandboxOrderRequest) -> SandboxOrderResult:
        if self._target != "sandbox-invest-public-api.tinkoff.ru:443":
            raise BrokerConfigurationError("Sandbox order requires sandbox target")
        from tinkoff.invest import OrderDirection as SdkDirection
        from tinkoff.invest import OrderType as SdkOrderType
        from tinkoff.invest.utils import decimal_to_quotation

        direction = getattr(SdkDirection, f"ORDER_DIRECTION_{request.direction.value}")
        order_type = getattr(SdkOrderType, f"ORDER_TYPE_{request.order_type.value}")
        async with self._client_factory(self._token, self._target) as client:
            response = await client.sandbox.post_sandbox_order(
                instrument_id=request.instrument_uid,
                quantity=request.quantity_lots,
                price=decimal_to_quotation(request.price),
                direction=direction,
                account_id=request.account_id,
                order_type=order_type,
                order_id=request.order_id,
            )
        return SandboxOrderResult(
            broker_order_id=response.order_id,
            broker_status=_enum_name(response.execution_report_status),
            lots_requested=response.lots_requested,
            lots_executed=response.lots_executed,
            execution_price=_decimal(response.executed_order_price),
            total_amount=_decimal(response.total_order_amount),
        )

    async def stream_portfolio(
        self, account_ids: Sequence[str]
    ) -> AsyncIterator[BrokerStreamEvent]:
        async with self._client_factory(self._token, self._target) as client:
            async for response in client.operations_stream.portfolio_stream(
                accounts=list(account_ids)
            ):
                now = datetime.now(UTC)
                if response.ping:
                    yield self._ping_event("PORTFOLIO", response.ping.time, now)
                elif response.subscriptions:
                    for item in response.subscriptions.accounts:
                        yield BrokerStreamEvent(
                            "tinvest",
                            self._target,
                            "PORTFOLIO",
                            item.account_id,
                            None,
                            now,
                            "SUBSCRIPTION_STATUS",
                            None,
                            {"status": _enum_name(item.subscription_status)},
                        )
                elif response.portfolio:
                    item = response.portfolio
                    yield BrokerStreamEvent(
                        "tinvest",
                        self._target,
                        "PORTFOLIO",
                        item.account_id,
                        None,
                        now,
                        "PORTFOLIO_UPDATED",
                        None,
                        {
                            "total_amount": str(_decimal(item.total_amount_portfolio)),
                            "currency": item.total_amount_portfolio.currency,
                            "positions_count": len(item.positions),
                        },
                    )

    async def stream_positions(
        self, account_ids: Sequence[str]
    ) -> AsyncIterator[BrokerStreamEvent]:
        async with self._client_factory(self._token, self._target) as client:
            async for response in client.operations_stream.positions_stream(
                accounts=list(account_ids)
            ):
                now = datetime.now(UTC)
                if response.ping:
                    yield self._ping_event("POSITIONS", response.ping.time, now)
                elif response.subscriptions:
                    for item in response.subscriptions.accounts:
                        yield BrokerStreamEvent(
                            "tinvest",
                            self._target,
                            "POSITIONS",
                            item.account_id,
                            None,
                            now,
                            "SUBSCRIPTION_STATUS",
                            None,
                            {"status": _enum_name(item.subscription_status)},
                        )
                elif response.position:
                    item = response.position
                    yield BrokerStreamEvent(
                        "tinvest",
                        self._target,
                        "POSITIONS",
                        item.account_id,
                        item.date,
                        now,
                        "POSITIONS_UPDATED",
                        None,
                        {
                            "money": [
                                {
                                    "amount": str(_decimal(value.available_value)),
                                    "currency": value.available_value.currency,
                                }
                                for value in item.money
                            ],
                            "securities_count": len(item.securities),
                        },
                    )

    async def stream_user_trades(
        self, account_ids: Sequence[str]
    ) -> AsyncIterator[BrokerStreamEvent]:
        async with self._client_factory(self._token, self._target) as client:
            async for response in client.orders_stream.trades_stream(accounts=list(account_ids)):
                now = datetime.now(UTC)
                if response.ping:
                    yield self._ping_event("TRADES", response.ping.time, now)
                elif response.order_trades:
                    item = response.order_trades
                    trades = [
                        {
                            "trade_id": trade.trade_id,
                            "quantity": trade.quantity,
                            "price": str(_decimal(trade.price)),
                            "created_at": trade.date_time.isoformat(),
                        }
                        for trade in item.trades
                    ]
                    yield BrokerStreamEvent(
                        "tinvest",
                        self._target,
                        "TRADES",
                        item.account_id,
                        item.created_at,
                        now,
                        "USER_TRADE_EXECUTED",
                        ",".join(sorted(trade["trade_id"] for trade in trades)),
                        {
                            "order_id": item.order_id,
                            "instrument_uid": item.instrument_uid,
                            "figi": item.figi,
                            "direction": _enum_name(item.direction),
                            "trades": trades,
                        },
                    )

    async def get_operations_page(self, request: OperationsCursorRequest) -> OperationsCursorPage:
        from tinkoff.invest import GetOperationsByCursorRequest, OperationState

        sdk_request = GetOperationsByCursorRequest(
            account_id=request.account_id,
            from_=request.from_,
            to=request.to,
            cursor=request.cursor or "",
            limit=request.limit,
            state=OperationState.OPERATION_STATE_EXECUTED,
            without_commissions=False,
            without_trades=False,
            without_overnights=True,
        )
        async with self._client_factory(self._token, self._target) as client:
            response = await client.operations.get_operations_by_cursor(request=sdk_request)
        return OperationsCursorPage(
            items=tuple(
                BrokerOperation(
                    operation_id=item.id,
                    cursor=item.cursor,
                    operation_type=_enum_name(item.type),
                    state=_enum_name(item.state),
                    payment=MoneyData(_decimal(item.payment), item.payment.currency),
                    date=item.date,
                    instrument_uid=item.instrument_uid or None,
                )
                for item in response.items
            ),
            next_cursor=response.next_cursor or None,
            has_next=response.has_next,
        )

    def _ping_event(
        self, stream_type: str, broker_time: datetime, received_at: datetime
    ) -> BrokerStreamEvent:
        return BrokerStreamEvent(
            "tinvest",
            self._target,
            stream_type,
            "",
            broker_time,
            received_at,
            "PING",
            None,
            {},
        )
