from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.models.enums import OrderDirection, OrderType


class CandleInterval(StrEnum):
    HOUR = "1h"
    DAY = "1d"


@dataclass(frozen=True, slots=True)
class BrokerAccountData:
    account_id: str
    name: str
    status: str
    account_type: str
    opened_at: datetime | None


@dataclass(frozen=True, slots=True)
class MoneyData:
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class PositionData:
    instrument_uid: str
    figi: str
    quantity: Decimal
    current_price: MoneyData
    average_price: MoneyData | None


@dataclass(frozen=True, slots=True)
class PortfolioData:
    account_id: str
    total_amount: MoneyData
    expected_yield: Decimal
    positions: tuple[PositionData, ...]
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class InstrumentData:
    instrument_uid: str
    figi: str
    ticker: str
    class_code: str
    name: str
    instrument_type: str
    currency: str
    lot: int
    api_trade_available: bool


@dataclass(frozen=True, slots=True)
class CandleData:
    instrument_uid: str
    interval: CandleInterval
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_complete: bool


@dataclass(frozen=True, slots=True)
class LastPriceData:
    instrument_uid: str
    price: Decimal
    time: datetime


@dataclass(frozen=True, slots=True)
class TradingStatusData:
    instrument_uid: str
    api_trade_available: bool
    market_order_available: bool
    limit_order_available: bool


@dataclass(frozen=True, slots=True)
class SandboxOrderRequest:
    account_id: str
    instrument_uid: str
    quantity_lots: int
    direction: OrderDirection
    order_type: OrderType
    price: Decimal
    order_id: str


@dataclass(frozen=True, slots=True)
class SandboxOrderResult:
    broker_order_id: str
    broker_status: str
    lots_requested: int
    lots_executed: int
    execution_price: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class BrokerCapabilities:
    portfolio_stream_supported: bool = False
    positions_stream_supported: bool = False
    trades_stream_supported: bool = False
    operations_cursor_supported: bool = False


@dataclass(frozen=True, slots=True)
class BrokerStreamEvent:
    provider: str
    target: str
    stream_type: str
    account_id: str
    broker_event_time: datetime | None
    received_at: datetime
    event_kind: str
    source_event_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OperationsCursorRequest:
    account_id: str
    from_: datetime
    to: datetime
    cursor: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class BrokerOperation:
    operation_id: str
    cursor: str
    operation_type: str
    state: str
    payment: MoneyData
    date: datetime
    instrument_uid: str | None


@dataclass(frozen=True, slots=True)
class OperationsCursorPage:
    items: tuple[BrokerOperation, ...]
    next_cursor: str | None
    has_next: bool
