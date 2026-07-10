"""Create automation runs.

Revision ID: 20260710_0007
Revises: 20260706_0006
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260710_0007"
down_revision: str | None = "20260706_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE automation_trigger AS ENUM "
        "('MANUAL', 'SCHEDULED', 'ACCOUNT_CHANGE', 'DEPOSIT_DETECTED', 'RECOVERY')"
    )
    op.execute(
        "CREATE TYPE automation_run_status AS ENUM "
        "('PENDING', 'RUNNING', 'SUCCEEDED', 'SKIPPED', 'FAILED', 'CANCELLED')"
    )
    op.execute(
        "CREATE TYPE automation_step AS ENUM "
        "('SAFETY_CHECK', 'ACCOUNT_SYNC', 'PORTFOLIO_SYNC', 'MARKET_DATA_SYNC', "
        "'SIGNAL_ANALYSIS', 'PORTFOLIO_OPTIMIZATION', 'REBALANCE_PLANNING', "
        "'EXECUTION_PLANNING', 'MODE_EXECUTION', 'FINAL_RECONCILIATION', 'COMPLETED')"
    )
    op.execute(
        """
        CREATE TABLE automation_runs (
            id UUID PRIMARY KEY,
            trigger automation_trigger NOT NULL,
            status automation_run_status NOT NULL,
            trade_mode trade_mode NOT NULL,
            started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL,
            heartbeat_at TIMESTAMPTZ NULL,
            account_id VARCHAR(128) NULL,
            correlation_id VARCHAR(128) NOT NULL UNIQUE,
            current_step automation_step NOT NULL,
            signals_count INTEGER NOT NULL DEFAULT 0,
            rebalance_plan_id UUID NULL REFERENCES rebalance_plans(id) ON DELETE SET NULL,
            planned_orders_count INTEGER NOT NULL DEFAULT 0,
            executed_orders_count INTEGER NOT NULL DEFAULT 0,
            virtual_trades_count INTEGER NOT NULL DEFAULT 0,
            error_code VARCHAR(64) NULL,
            error_message TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_automation_runs_status_heartbeat ON automation_runs (status, heartbeat_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_automation_runs_status_heartbeat")
    op.execute("DROP TABLE IF EXISTS automation_runs")
    op.execute("DROP TYPE IF EXISTS automation_step")
    op.execute("DROP TYPE IF EXISTS automation_run_status")
    op.execute("DROP TYPE IF EXISTS automation_trigger")
