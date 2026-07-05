"""Create rebalance plans and target allocations.

Revision ID: 20260706_0003
Revises: 20260706_0002
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260706_0003"
down_revision: str | None = "20260706_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

plan_status = postgresql.ENUM(
    "DRAFT", "APPROVED", "REJECTED", "EXECUTED", name="rebalance_plan_status", create_type=False
)
allocation_action = postgresql.ENUM(
    "BUY", "SELL", "HOLD", name="allocation_action", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    plan_status.create(bind, checkfirst=True)
    allocation_action.create(bind, checkfirst=True)
    op.create_table(
        "rebalance_plans",
        sa.Column("source_account_id", sa.String(128), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.Column("portfolio_value", sa.Numeric(24, 9), nullable=False),
        sa.Column("cash_available", sa.Numeric(24, 9), nullable=False),
        sa.Column("target_cash_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rebalance_plans")),
    )
    op.create_table(
        "target_allocations",
        sa.Column("rebalance_plan_id", sa.UUID(), nullable=False),
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("target_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("current_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("signal_score", sa.Numeric(8, 6), nullable=False),
        sa.Column("target_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column("delta_amount", sa.Numeric(24, 9), nullable=False),
        sa.Column("action", allocation_action, nullable=False),
        sa.Column("recommended_lots", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_target_allocations_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rebalance_plan_id"],
            ["rebalance_plans.id"],
            name=op.f("fk_target_allocations_rebalance_plan_id_rebalance_plans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_target_allocations")),
        sa.UniqueConstraint(
            "rebalance_plan_id",
            "instrument_id",
            name=op.f("uq_target_allocations_rebalance_plan_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("target_allocations")
    op.drop_table("rebalance_plans")
    bind = op.get_bind()
    allocation_action.drop(bind, checkfirst=True)
    plan_status.drop(bind, checkfirst=True)
