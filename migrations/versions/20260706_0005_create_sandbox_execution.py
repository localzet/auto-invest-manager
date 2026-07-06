"""Create sandbox execution orders and events.

Revision ID: 20260706_0005
Revises: 20260706_0004
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260706_0005"
down_revision: str | None = "20260706_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE planned_order_status ADD VALUE IF NOT EXISTS 'SUBMITTED'")
    op.create_table(
        "execution_orders",
        sa.Column("planned_order_id", sa.UUID(), nullable=False),
        sa.Column("broker_order_id", sa.String(128), nullable=False),
        sa.Column("broker_status", sa.String(64), nullable=False),
        sa.Column("lots_requested", sa.Integer(), nullable=False),
        sa.Column("lots_executed", sa.Integer(), nullable=False),
        sa.Column("execution_price", sa.Numeric(24, 9), nullable=False),
        sa.Column("total_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column(
            "trade_mode", postgresql.ENUM(name="trade_mode", create_type=False), nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["planned_order_id"], ["planned_orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_orders")),
        sa.UniqueConstraint("broker_order_id", name=op.f("uq_execution_orders_broker_order_id")),
        sa.UniqueConstraint("planned_order_id", name=op.f("uq_execution_orders_planned_order_id")),
    )
    op.create_table(
        "order_events",
        sa.Column("execution_order_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("broker_status", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_order_id"], ["execution_orders.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_events")),
    )


def downgrade() -> None:
    op.drop_table("order_events")
    op.drop_table("execution_orders")
