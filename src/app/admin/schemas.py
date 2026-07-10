from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.broker.dto import BrokerAccountData
from app.models.enums import (
    AllocationAction,
    OrderDirection,
    OrderType,
    PlannedOrderStatus,
    RebalanceMode,
    RebalancePlanStatus,
    RiskMode,
    SignalRecommendation,
    TradeMode,
)

Weight = Annotated[Decimal, Field(ge=0, le=1, max_digits=8, decimal_places=6)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=9)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SystemSettingsResponse(ORMModel):
    id: UUID
    trade_mode: TradeMode
    kill_switch: bool
    updated_at: datetime
    real_trading_enabled_by_env: bool


class SystemSettingsUpdate(BaseModel):
    trade_mode: TradeMode | None = None
    kill_switch: bool | None = None


class InstrumentReference(BaseModel):
    ticker: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    class_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class InstrumentResponse(ORMModel):
    id: UUID
    instrument_uid: str
    figi: str | None
    ticker: str
    class_code: str
    name: str
    instrument_type: str
    currency: str
    lot: int
    is_active: bool


class InstrumentSyncRequest(BaseModel):
    instruments: list[InstrumentReference] = Field(min_length=1, max_length=100)


class WatchlistItemCreate(InstrumentReference):
    buy_enabled: bool = True
    sell_enabled: bool = True
    max_weight: Weight | None = None
    priority: int = Field(default=0, ge=0, le=10_000)
    min_signal_score: Weight = Decimal("0.5")
    manual_target_weight: Weight | None = None

    @model_validator(mode="after")
    def validate_target_weight(self) -> "WatchlistItemCreate":
        if (
            self.max_weight is not None
            and self.manual_target_weight is not None
            and self.manual_target_weight > self.max_weight
        ):
            raise ValueError("manual_target_weight cannot exceed max_weight")
        return self


class WatchlistItemUpdate(BaseModel):
    buy_enabled: bool | None = None
    sell_enabled: bool | None = None
    max_weight: Weight | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)
    min_signal_score: Weight | None = None
    manual_target_weight: Weight | None = None


class WatchlistItemResponse(ORMModel):
    id: UUID
    buy_enabled: bool
    sell_enabled: bool
    max_weight: Decimal | None
    priority: int
    min_signal_score: Decimal
    manual_target_weight: Decimal | None
    instrument: InstrumentResponse
    updated_at: datetime


class RiskProfileUpdate(BaseModel):
    mode: RiskMode | None = None
    max_position_weight: Weight | None = None
    max_sector_weight: Weight | None = None
    min_cash_weight: Weight | None = None
    max_daily_trades: int | None = Field(default=None, ge=0, le=10_000)
    max_trade_amount: PositiveMoney | None = None
    max_portfolio_drawdown: Weight | None = None
    max_daily_drawdown: Weight | None = None
    allow_short_selling: bool | None = None
    allow_margin_trading: bool | None = None
    allow_futures: bool | None = None
    default_order_type: OrderType | None = None
    max_slippage_percent: Weight | None = None
    trade_cooldown_seconds: int | None = Field(default=None, ge=0, le=31_536_000)
    rebalance_threshold_percent: Weight | None = None


class RiskProfileResponse(ORMModel):
    id: UUID
    name: str
    mode: RiskMode
    is_active: bool
    max_position_weight: Decimal
    max_sector_weight: Decimal | None
    min_cash_weight: Decimal
    max_daily_trades: int
    max_trade_amount: Decimal
    max_portfolio_drawdown: Decimal
    max_daily_drawdown: Decimal
    allow_short_selling: bool
    allow_margin_trading: bool
    allow_futures: bool
    default_order_type: OrderType
    max_slippage_percent: Decimal
    trade_cooldown_seconds: int
    rebalance_threshold_percent: Decimal
    updated_at: datetime


class StrategyProfileUpdate(BaseModel):
    enabled: bool | None = None
    trade_mode: TradeMode | None = None
    auto_allocation_enabled: bool | None = None
    rebalance_mode: RebalanceMode | None = None
    signal_threshold: Weight | None = None
    minimum_expected_return: Weight | None = None
    prefer_cash_when_no_signal: bool | None = None
    use_protective_asset: bool | None = None
    max_wait_days: int | None = Field(default=None, ge=0, le=3650)
    base_timeframe: Literal["1h", "1d"] | None = None


class StrategyProfileResponse(ORMModel):
    id: UUID
    name: str
    enabled: bool
    trade_mode: TradeMode
    auto_allocation_enabled: bool
    rebalance_mode: RebalanceMode
    signal_threshold: Decimal
    minimum_expected_return: Decimal
    prefer_cash_when_no_signal: bool
    use_protective_asset: bool
    max_wait_days: int
    base_timeframe: str
    updated_at: datetime


class AccountsResponse(BaseModel):
    accounts: tuple[BrokerAccountData, ...]


class SignalResponse(ORMModel):
    id: UUID
    instrument: InstrumentResponse
    timeframe: str
    trend_score: Decimal
    moving_average_score: Decimal
    volatility_score: Decimal
    volume_score: Decimal
    drawdown_score: Decimal
    final_score: Decimal
    recommendation: SignalRecommendation
    price: Decimal
    reason: str
    model_version: str
    calculated_at: datetime


class AnalysisRunResponse(BaseModel):
    signals: list[SignalResponse]


class TargetAllocationResponse(ORMModel):
    id: UUID
    instrument: InstrumentResponse
    target_weight: Decimal
    current_weight: Decimal
    signal_score: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    action: AllocationAction
    recommended_lots: int
    reason: str


class RebalancePlanResponse(ORMModel):
    id: UUID
    source_account_id: str
    status: RebalancePlanStatus
    portfolio_value: Decimal
    cash_available: Decimal
    target_cash_weight: Decimal
    reason: str
    created_at: datetime
    allocations: list[TargetAllocationResponse]


class PlannedOrderResponse(ORMModel):
    id: UUID
    instrument: InstrumentResponse
    account_id: str
    direction: OrderDirection
    lots: int
    order_type: OrderType
    limit_price: Decimal
    reason: str
    status: PlannedOrderStatus
    trade_mode: TradeMode
    idempotency_key: str
    created_at: datetime


class VirtualTradeResponse(ORMModel):
    id: UUID
    instrument: InstrumentResponse
    direction: OrderDirection
    lots: int
    price: Decimal
    total_amount: Decimal
    executed_at: datetime


class ExecutionOrderResponse(ORMModel):
    id: UUID
    planned_order_id: UUID
    broker_order_id: str
    broker_status: str
    lots_requested: int
    lots_executed: int
    execution_price: Decimal
    total_amount: Decimal
    trade_mode: TradeMode
    created_at: datetime


class AuditLogResponse(ORMModel):
    id: UUID
    event_type: str
    severity: str
    actor: str
    message: str
    context: dict[str, object]
    created_at: datetime
