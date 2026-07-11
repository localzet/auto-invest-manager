from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AccountEventType,
    AllocationAction,
    AutomationRunStatus,
    AutomationStep,
    AutomationTrigger,
    BrokerStreamEventKind,
    BrokerStreamStatus,
    BrokerStreamType,
    OrderDirection,
    OrderType,
    PlannedOrderStatus,
    RebalanceMode,
    RebalancePlanStatus,
    ReconciliationStatus,
    RiskMode,
    SignalRecommendation,
    StreamEventProcessingStatus,
    TradeMode,
)

MONEY = Numeric(24, 9)
WEIGHT = Numeric(8, 6)


class SystemSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    trade_mode: Mapped[TradeMode] = mapped_column(
        Enum(TradeMode, name="trade_mode"), default=TradeMode.OFF, nullable=False
    )
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BrokerAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_accounts"

    broker_account_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Instrument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("ticker", "class_code"),)

    instrument_uid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    figi: Mapped[str | None] = mapped_column(String(64), unique=True)
    ticker: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    class_code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    lot: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WatchlistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_items"

    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    buy_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sell_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_weight: Mapped[Decimal | None] = mapped_column(WEIGHT)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_signal_score: Mapped[Decimal] = mapped_column(
        WEIGHT, default=Decimal("0.5"), nullable=False
    )
    manual_target_weight: Mapped[Decimal | None] = mapped_column(WEIGHT)
    instrument: Mapped["Instrument"] = relationship(lazy="raise")


class RiskProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_profiles"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    mode: Mapped[RiskMode] = mapped_column(Enum(RiskMode, name="risk_mode"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_position_weight: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    max_sector_weight: Mapped[Decimal | None] = mapped_column(WEIGHT)
    min_cash_weight: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    max_daily_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    max_trade_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    max_portfolio_drawdown: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    max_daily_drawdown: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    allow_short_selling: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_margin_trading: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_futures: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type"), default=OrderType.LIMIT, nullable=False
    )
    max_slippage_percent: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    trade_cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rebalance_threshold_percent: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)


class StrategyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strategy_profiles"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trade_mode: Mapped[TradeMode] = mapped_column(
        Enum(TradeMode, name="trade_mode"), nullable=False
    )
    auto_allocation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rebalance_mode: Mapped[RebalanceMode] = mapped_column(
        Enum(RebalanceMode, name="rebalance_mode"), nullable=False
    )
    signal_threshold: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    minimum_expected_return: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    prefer_cash_when_no_signal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_protective_asset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_wait_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_timeframe: Mapped[str] = mapped_column(String(8), default="1d", nullable=False)


class PortfolioSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_account_captured", "account_id", "captured_at"),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("broker_accounts.id", ondelete="CASCADE"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    expected_yield: Mapped[Decimal | None] = mapped_column(WEIGHT)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CashSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cash_snapshots"

    portfolio_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class Position(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_snapshot_id", "instrument_id"),)

    portfolio_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    current_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(MONEY)


class MarketCandle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "market_candles"
    __table_args__ = (UniqueConstraint("instrument_id", "interval", "time"),)

    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    high: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    low: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    close: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class MarketPrice(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "market_prices"
    __table_args__ = (Index("ix_market_prices_instrument_time", "instrument_id", "time"),)

    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class Signal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_instrument_calculated", "instrument_id", "calculated_at"),)

    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    trend_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    moving_average_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    volatility_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    volume_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    drawdown_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    final_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    recommendation: Mapped[SignalRecommendation] = mapped_column(
        Enum(SignalRecommendation, name="signal_recommendation"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument: Mapped["Instrument"] = relationship(lazy="raise")


class RebalancePlan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rebalance_plans"

    source_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[RebalancePlanStatus] = mapped_column(
        Enum(RebalancePlanStatus, name="rebalance_plan_status"), nullable=False
    )
    portfolio_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_available: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    target_cash_weight: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    allocations: Mapped[list["TargetAllocation"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="raise"
    )


class TargetAllocation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "target_allocations"
    __table_args__ = (UniqueConstraint("rebalance_plan_id", "instrument_id"),)

    rebalance_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("rebalance_plans.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    target_weight: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    current_weight: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    signal_score: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    delta_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    action: Mapped[AllocationAction] = mapped_column(
        Enum(AllocationAction, name="allocation_action"), nullable=False
    )
    recommended_lots: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped["RebalancePlan"] = relationship(back_populates="allocations", lazy="raise")
    instrument: Mapped["Instrument"] = relationship(lazy="raise")


class PlannedOrder(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "planned_orders"

    rebalance_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("rebalance_plans.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[OrderDirection] = mapped_column(
        Enum(OrderDirection, name="order_direction"), nullable=False
    )
    lots: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type", create_type=False), nullable=False
    )
    limit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PlannedOrderStatus] = mapped_column(
        Enum(PlannedOrderStatus, name="planned_order_status"), nullable=False
    )
    trade_mode: Mapped[TradeMode] = mapped_column(
        Enum(TradeMode, name="trade_mode", create_type=False), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    instrument: Mapped["Instrument"] = relationship(lazy="raise")
    virtual_trade: Mapped["VirtualTrade | None"] = relationship(
        back_populates="planned_order", uselist=False, lazy="raise"
    )


class VirtualTrade(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "virtual_trades"

    planned_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("planned_orders.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    direction: Mapped[OrderDirection] = mapped_column(
        Enum(OrderDirection, name="order_direction", create_type=False), nullable=False
    )
    lots: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    planned_order: Mapped["PlannedOrder"] = relationship(
        back_populates="virtual_trade", lazy="raise"
    )
    instrument: Mapped["Instrument"] = relationship(lazy="raise")


class ExecutionOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "execution_orders"

    planned_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("planned_orders.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    broker_order_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    broker_status: Mapped[str] = mapped_column(String(64), nullable=False)
    lots_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    lots_executed: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    trade_mode: Mapped[TradeMode] = mapped_column(
        Enum(TradeMode, name="trade_mode", create_type=False), nullable=False
    )
    planned_order: Mapped["PlannedOrder"] = relationship(lazy="raise")
    events: Mapped[list["OrderEvent"]] = relationship(
        back_populates="execution_order", cascade="all, delete-orphan", lazy="raise"
    )


class OrderEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_events"

    execution_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_orders.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    execution_order: Mapped["ExecutionOrder"] = relationship(back_populates="events", lazy="raise")


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"

    event_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class AutomationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_runs"
    __table_args__ = (Index("ix_automation_runs_status_heartbeat", "status", "heartbeat_at"),)

    trigger: Mapped[AutomationTrigger] = mapped_column(
        Enum(AutomationTrigger, name="automation_trigger"), nullable=False
    )
    status: Mapped[AutomationRunStatus] = mapped_column(
        Enum(AutomationRunStatus, name="automation_run_status"), nullable=False
    )
    trade_mode: Mapped[TradeMode] = mapped_column(
        Enum(TradeMode, name="trade_mode", create_type=False), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_id: Mapped[str | None] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    current_step: Mapped[AutomationStep] = mapped_column(
        Enum(AutomationStep, name="automation_step"), nullable=False
    )
    signals_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rebalance_plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("rebalance_plans.id", ondelete="SET NULL")
    )
    planned_orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    executed_orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    virtual_trades_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class BrokerStreamEventRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_stream_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key"),
        Index("ix_broker_stream_events_processing", "processing_status", "next_attempt_at"),
    )

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    stream_type: Mapped[BrokerStreamType] = mapped_column(
        Enum(BrokerStreamType, name="broker_stream_type"), nullable=False
    )
    event_kind: Mapped[BrokerStreamEventKind] = mapped_column(
        Enum(BrokerStreamEventKind, name="broker_stream_event_kind"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(255))
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processing_status: Mapped[StreamEventProcessingStatus] = mapped_column(
        Enum(StreamEventProcessingStatus, name="stream_event_processing_status"),
        nullable=False,
    )
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


class BrokerStreamState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_stream_states"
    __table_args__ = (UniqueConstraint("provider", "target", "stream_type", "account_set_hash"),)

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    stream_type: Mapped[BrokerStreamType] = mapped_column(
        Enum(BrokerStreamType, name="broker_stream_type", create_type=False), nullable=False
    )
    account_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[BrokerStreamStatus] = mapped_column(
        Enum(BrokerStreamStatus, name="broker_stream_status"), nullable=False
    )
    instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    next_reconnect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_status: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class BrokerOperationCursor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "broker_operation_cursors"
    __table_args__ = (UniqueConstraint("account_id", "provider", "target"),)

    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(512))
    last_operation_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_operation_fingerprint: Mapped[str | None] = mapped_column(String(64))


class AccountEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "account_events"
    __table_args__ = (UniqueConstraint("fingerprint"),)

    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[AccountEventType] = mapped_column(
        Enum(AccountEventType, name="account_event_type"), nullable=False
    )
    operation_id: Mapped[str | None] = mapped_column(String(128))
    operation_type: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(8))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )


class AccountReconciliation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "account_reconciliations"

    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status"), nullable=False
    )
    reasons: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    account_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    automation_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="SET NULL")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
