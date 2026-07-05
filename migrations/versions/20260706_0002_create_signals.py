"""Create signals table.

Revision ID: 20260706_0002
Revises: 20260706_0001
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_0002"
down_revision: str | None = "20260706_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    recommendation = sa.Enum("BUY", "HOLD", "SELL", "WAIT", name="signal_recommendation")
    op.create_table(
        "signals",
        sa.Column("instrument_id", sa.UUID(), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("trend_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("moving_average_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("volatility_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("volume_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("drawdown_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("final_score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("recommendation", recommendation, nullable=False),
        sa.Column("price", sa.Numeric(precision=24, scale=9), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_signals_instrument_id_instruments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
    )
    op.create_index(
        "ix_signals_instrument_calculated",
        "signals",
        ["instrument_id", "calculated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signals_instrument_calculated", table_name="signals")
    op.drop_table("signals")
    sa.Enum(name="signal_recommendation").drop(op.get_bind(), checkfirst=True)
