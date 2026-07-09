"""Add manual confirmation statuses.

Revision ID: 20260706_0006
Revises: 20260706_0005
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260706_0006"
down_revision: str | None = "20260706_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE planned_order_status ADD VALUE IF NOT EXISTS 'APPROVED'")
    op.execute("ALTER TYPE planned_order_status ADD VALUE IF NOT EXISTS 'REJECTED'")


def downgrade() -> None:
    # PostgreSQL enum values are removed when the type is dropped by migration 0004.
    pass
