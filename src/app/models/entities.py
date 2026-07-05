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
    AllocationAction,
    OrderType,
    RebalanceMode,
    RebalancePlanStatus,
    RiskMode,
    SignalRecommendation,
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
