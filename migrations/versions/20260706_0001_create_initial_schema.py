"""Create initial schema.

Revision ID: 20260706_0001
Revises:
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260706_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

trade_mode = postgresql.ENUM(
    "OFF",
    "SIGNAL_ONLY",
    "DRY_RUN",
    "SANDBOX",
    "REAL_MANUAL_CONFIRM",
    "REAL_AUTO_SAFE",
    name="trade_mode",
    create_type=False,
)
risk_mode = postgresql.ENUM(
    "CONSERVATIVE", "BALANCED", "AGGRESSIVE", "CUSTOM", name="risk_mode", create_type=False
)
order_type = postgresql.ENUM("LIMIT", "MARKET", name="order_type", create_type=False)
rebalance_mode = postgresql.ENUM(
    "ON_DEPOSIT", "DAILY", "WEEKLY", "THRESHOLD", "MANUAL", name="rebalance_mode", create_type=False
)


def _id() -> sa.Column[object]:
    return sa.Column("id", sa.UUID(), nullable=False)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (trade_mode, risk_mode, order_type, rebalance_mode):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "audit_logs",
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _id(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index(op.f("ix_audit_logs_event_type"), "audit_logs", ["event_type"])

    op.create_table(
        "broker_accounts",
        sa.Column("broker_account_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("is_sandbox", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _id(),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_accounts")),
        sa.UniqueConstraint("broker_account_id", name=op.f("uq_broker_accounts_broker_account_id")),
    )
    op.create_table(
        "instruments",
        sa.Column("instrument_uid", sa.String(128), nullable=False),
        sa.Column("figi", sa.String(64), nullable=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("class_code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("instrument_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("lot", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _id(),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint("figi", name=op.f("uq_instruments_figi")),
        sa.UniqueConstraint("instrument_uid", name=op.f("uq_instruments_instrument_uid")),
        sa.UniqueConstraint("ticker", "class_code", name=op.f("uq_instruments_ticker")),
    )
    op.create_index(op.f("ix_instruments_ticker"), "instruments", ["ticker"])
    op.create_table(
        "risk_profiles",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("mode", risk_mode, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("max_position_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("max_sector_weight", sa.Numeric(8, 6), nullable=True),
        sa.Column("min_cash_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("max_daily_trades", sa.Integer(), nullable=False),
        sa.Column("max_trade_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column("max_portfolio_drawdown", sa.Numeric(8, 6), nullable=False),
        sa.Column("max_daily_drawdown", sa.Numeric(8, 6), nullable=False),
        sa.Column("allow_short_selling", sa.Boolean(), nullable=False),
        sa.Column("allow_margin_trading", sa.Boolean(), nullable=False),
        sa.Column("allow_futures", sa.Boolean(), nullable=False),
        sa.Column("default_order_type", order_type, nullable=False),
        sa.Column("max_slippage_percent", sa.Numeric(8, 6), nullable=False),
        sa.Column("trade_cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("rebalance_threshold_percent", sa.Numeric(8, 6), nullable=False),
        _id(),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_risk_profiles_name")),
    )
    op.create_table(
        "strategy_profiles",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trade_mode", trade_mode, nullable=False),
        sa.Column("auto_allocation_enabled", sa.Boolean(), nullable=False),
        sa.Column("rebalance_mode", rebalance_mode, nullable=False),
        sa.Column("signal_threshold", sa.Numeric(8, 6), nullable=False),
        sa.Column("minimum_expected_return", sa.Numeric(8, 6), nullable=False),
        sa.Column("prefer_cash_when_no_signal", sa.Boolean(), nullable=False),
        sa.Column("use_protective_asset", sa.Boolean(), nullable=False),
        sa.Column("max_wait_days", sa.Integer(), nullable=False),
        sa.Column("base_timeframe", sa.String(8), nullable=False),
        _id(),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_strategy_profiles_name")),
    )
    op.create_table(
        "system_settings",
        sa.Column("trade_mode", trade_mode, nullable=False),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        _id(),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_settings")),
    )
    op.create_table(
        "market_candles",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("interval", sa.String(16), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 9), nullable=False),
        sa.Column("high", sa.Numeric(24, 9), nullable=False),
        sa.Column("low", sa.Numeric(24, 9), nullable=False),
        sa.Column("close", sa.Numeric(24, 9), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        _id(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_market_candles_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_candles")),
        sa.UniqueConstraint(
            "instrument_id", "interval", "time", name=op.f("uq_market_candles_instrument_id")
        ),
    )
    op.create_table(
        "market_prices",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("price", sa.Numeric(24, 9), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        _id(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_market_prices_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_prices")),
    )
    op.create_index("ix_market_prices_instrument_time", "market_prices", ["instrument_id", "time"])
    op.create_table(
        "portfolio_snapshots",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("total_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column("expected_yield", sa.Numeric(8, 6), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        _id(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_portfolio_snapshots_account_id_broker_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_snapshots")),
    )
    op.create_index(
        "ix_portfolio_snapshots_account_captured",
        "portfolio_snapshots",
        ["account_id", "captured_at"],
    )
    op.create_table(
        "watchlist_items",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("buy_enabled", sa.Boolean(), nullable=False),
        sa.Column("sell_enabled", sa.Boolean(), nullable=False),
        sa.Column("max_weight", sa.Numeric(8, 6), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("min_signal_score", sa.Numeric(8, 6), nullable=False),
        sa.Column("manual_target_weight", sa.Numeric(8, 6), nullable=True),
        _id(),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_watchlist_items_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint("instrument_id", name=op.f("uq_watchlist_items_instrument_id")),
    )
    op.create_table(
        "cash_snapshots",
        sa.Column("portfolio_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(24, 9), nullable=False),
        _id(),
        sa.ForeignKeyConstraint(
            ["portfolio_snapshot_id"],
            ["portfolio_snapshots.id"],
            name=op.f("fk_cash_snapshots_portfolio_snapshot_id_portfolio_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_snapshots")),
    )
    op.create_table(
        "positions",
        sa.Column("portfolio_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 9), nullable=False),
        sa.Column("current_price", sa.Numeric(24, 9), nullable=False),
        sa.Column("current_value", sa.Numeric(24, 9), nullable=False),
        sa.Column("average_price", sa.Numeric(24, 9), nullable=True),
        _id(),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_positions_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_snapshot_id"],
            ["portfolio_snapshots.id"],
            name=op.f("fk_positions_portfolio_snapshot_id_portfolio_snapshots"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "portfolio_snapshot_id",
            "instrument_id",
            name=op.f("uq_positions_portfolio_snapshot_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_table("cash_snapshots")
    op.drop_table("watchlist_items")
    op.drop_index("ix_portfolio_snapshots_account_captured", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_index("ix_market_prices_instrument_time", table_name="market_prices")
    op.drop_table("market_prices")
    op.drop_table("market_candles")
    op.drop_table("system_settings")
    op.drop_table("strategy_profiles")
    op.drop_table("risk_profiles")
    op.drop_index(op.f("ix_instruments_ticker"), table_name="instruments")
    op.drop_table("instruments")
    op.drop_table("broker_accounts")
    op.drop_index(op.f("ix_audit_logs_event_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_table("audit_logs")
    bind = op.get_bind()
    for enum in reversed((trade_mode, risk_mode, order_type, rebalance_mode)):
        enum.drop(bind, checkfirst=True)
