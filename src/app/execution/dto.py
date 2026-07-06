from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import OrderDirection, OrderType, TradeMode


@dataclass(frozen=True, slots=True)
class ExecutionAllocation:
    instrument_uid: str
    ticker: str
    direction: OrderDirection
    lots: int
    lot_size: int
    market_price: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class PlannedOrderData:
    instrument_uid: str
    ticker: str
    direction: OrderDirection
    lots: int
    lot_size: int
    order_type: OrderType
    limit_price: Decimal
    reason: str
    trade_mode: TradeMode
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RiskContext:
    kill_switch: bool
    trade_mode: TradeMode
    required_trade_mode: TradeMode
    account_id: str
    expected_account_id: str
    in_watchlist: bool
    direction_allowed: bool
    api_trade_available: bool
    order_type_available: bool
    price_time: datetime
    now: datetime
    max_price_age_seconds: int
    market_price: Decimal
    max_slippage_percent: Decimal
    cash_available: Decimal
    current_position_lots: int
    current_position_value: Decimal
    portfolio_value: Decimal
    max_position_weight: Decimal
    max_trade_amount: Decimal
    daily_trades: int
    max_daily_trades: int
    cooldown_active: bool
    duplicate_active_order: bool
    idempotency_key_exists: bool


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]
