"""Create planned orders and virtual trades.

Revision ID: 20260706_0004
Revises: 20260706_0003
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260706_0004"
down_revision: str | None = "20260706_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

direction = postgresql.ENUM("BUY", "SELL", name="order_direction", create_type=False)
status = postgresql.ENUM(
    "PLANNED",
    "RISK_REJECTED",
    "SIMULATED",
    "SUBMITTED",
    "WAITING_CONFIRMATION",
    name="planned_order_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    direction.create(bind, checkfirst=True)
    status.create(bind, checkfirst=True)
    op.create_table(
        "planned_orders",
        sa.Column("rebalance_plan_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.String(128), nullable=False),
        sa.Column("direction", direction, nullable=False),
        sa.Column("lots", sa.Integer(), nullable=False),
        sa.Column(
            "order_type", postgresql.ENUM(name="order_type", create_type=False), nullable=False
        ),
        sa.Column("limit_price", sa.Numeric(24, 9), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column(
            "trade_mode", postgresql.ENUM(name="trade_mode", create_type=False), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rebalance_plan_id"], ["rebalance_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planned_orders")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_planned_orders_idempotency_key")),
    )
    op.create_table(
        "virtual_trades",
        sa.Column("planned_order_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("direction", direction, nullable=False),
        sa.Column("lots", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(24, 9), nullable=False),
        sa.Column("total_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["planned_order_id"], ["planned_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_virtual_trades")),
        sa.UniqueConstraint("planned_order_id", name=op.f("uq_virtual_trades_planned_order_id")),
    )


def downgrade() -> None:
    op.drop_table("virtual_trades")
    op.drop_table("planned_orders")
    bind = op.get_bind()
    status.drop(bind, checkfirst=True)
    direction.drop(bind, checkfirst=True)
