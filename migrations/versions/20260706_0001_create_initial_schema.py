"""Create initial schema.

Revision ID: 20260706_0001
Revises:
Create Date: 2026-07-06
"""

from collections.abc import Sequence

from alembic import op

from app import models  # noqa: F401
from app.db.base import Base

revision: str = "20260706_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = [table for table in Base.metadata.sorted_tables if table.name != "signals"]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [table for table in Base.metadata.sorted_tables if table.name != "signals"]
    Base.metadata.drop_all(bind=bind, tables=tables, checkfirst=False)
