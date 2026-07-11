"""Create stream inbox and account reconciliation tables.

Revision ID: 20260711_0008
Revises: 20260710_0007
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260711_0008"
down_revision: str | None = "20260710_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE broker_stream_type AS ENUM ('PORTFOLIO','POSITIONS','TRADES')")
    op.execute(
        "CREATE TYPE broker_stream_event_kind AS ENUM "
        "('PORTFOLIO_UPDATED','POSITIONS_UPDATED','USER_TRADE_EXECUTED',"
        "'SUBSCRIPTION_STATUS','PING')"
    )
    op.execute(
        "CREATE TYPE stream_event_processing_status AS ENUM "
        "('PENDING','PROCESSING','PROCESSED','IGNORED','FAILED','DEAD_LETTER')"
    )
    op.execute(
        "CREATE TYPE broker_stream_status AS ENUM "
        "('DISABLED','STARTING','CONNECTING','CONNECTED','DEGRADED',"
        "'RECONNECTING','FAILED','STOPPED')"
    )
    op.execute(
        "CREATE TYPE account_event_type AS ENUM "
        "('ACCOUNT_CHANGE','DEPOSIT_DETECTED','WITHDRAWAL_DETECTED',"
        "'ORDER_EXECUTION_DETECTED')"
    )
    op.execute(
        "CREATE TYPE reconciliation_status AS ENUM ('PENDING','RUNNING','SUCCEEDED','FAILED')"
    )
    op.execute(
        """
        CREATE TABLE broker_stream_events (
            id UUID PRIMARY KEY, provider VARCHAR(32) NOT NULL,
            target VARCHAR(128) NOT NULL, stream_type broker_stream_type NOT NULL,
            event_kind broker_stream_event_kind NOT NULL, account_id VARCHAR(128) NOT NULL,
            broker_event_time TIMESTAMPTZ NULL, received_at TIMESTAMPTZ NOT NULL,
            source_event_id VARCHAR(255) NULL, dedupe_key VARCHAR(64) NOT NULL UNIQUE,
            payload JSONB NOT NULL, processing_status stream_event_processing_status NOT NULL,
            processing_attempts INTEGER NOT NULL DEFAULT 0, processed_at TIMESTAMPTZ NULL,
            next_attempt_at TIMESTAMPTZ NULL, error_code VARCHAR(64) NULL,
            error_message TEXT NULL, correlation_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_broker_stream_events_processing "
        "ON broker_stream_events (processing_status, next_attempt_at)"
    )
    op.execute(
        """
        CREATE TABLE broker_stream_states (
            id UUID PRIMARY KEY, provider VARCHAR(32) NOT NULL,
            target VARCHAR(128) NOT NULL, stream_type broker_stream_type NOT NULL,
            account_set_hash VARCHAR(64) NOT NULL, status broker_stream_status NOT NULL,
            instance_id VARCHAR(64) NOT NULL, connected_at TIMESTAMPTZ NULL,
            disconnected_at TIMESTAMPTZ NULL, last_message_at TIMESTAMPTZ NULL,
            last_ping_at TIMESTAMPTZ NULL, last_event_at TIMESTAMPTZ NULL,
            reconnect_count INTEGER NOT NULL DEFAULT 0,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_error_code VARCHAR(64) NULL, last_error_message TEXT NULL,
            next_reconnect_at TIMESTAMPTZ NULL,
            subscription_status JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(provider,target,stream_type,account_set_hash)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE broker_operation_cursors (
            id UUID PRIMARY KEY, account_id VARCHAR(128) NOT NULL,
            provider VARCHAR(32) NOT NULL, target VARCHAR(128) NOT NULL,
            cursor VARCHAR(512) NULL, last_operation_time TIMESTAMPTZ NULL,
            last_successful_sync_at TIMESTAMPTZ NULL,
            last_operation_fingerprint VARCHAR(64) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(account_id,provider,target)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE account_events (
            id UUID PRIMARY KEY, account_id VARCHAR(128) NOT NULL,
            event_type account_event_type NOT NULL, operation_id VARCHAR(128) NULL,
            operation_type VARCHAR(128) NULL, amount NUMERIC(24,9) NULL,
            currency VARCHAR(8) NULL, occurred_at TIMESTAMPTZ NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE, correlation_id VARCHAR(128) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE account_reconciliations (
            id UUID PRIMARY KEY, account_id VARCHAR(128) NOT NULL,
            status reconciliation_status NOT NULL, reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            correlation_id VARCHAR(128) NOT NULL UNIQUE, started_at TIMESTAMPTZ NULL,
            finished_at TIMESTAMPTZ NULL, operations_count INTEGER NOT NULL DEFAULT 0,
            account_events_count INTEGER NOT NULL DEFAULT 0,
            automation_run_id UUID NULL REFERENCES automation_runs(id) ON DELETE SET NULL,
            error_code VARCHAR(64) NULL, error_message TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS account_reconciliations")
    op.execute("DROP TABLE IF EXISTS account_events")
    op.execute("DROP TABLE IF EXISTS broker_operation_cursors")
    op.execute("DROP TABLE IF EXISTS broker_stream_states")
    op.execute("DROP INDEX IF EXISTS ix_broker_stream_events_processing")
    op.execute("DROP TABLE IF EXISTS broker_stream_events")
    op.execute("DROP TYPE IF EXISTS reconciliation_status")
    op.execute("DROP TYPE IF EXISTS account_event_type")
    op.execute("DROP TYPE IF EXISTS broker_stream_status")
    op.execute("DROP TYPE IF EXISTS stream_event_processing_status")
    op.execute("DROP TYPE IF EXISTS broker_stream_event_kind")
    op.execute("DROP TYPE IF EXISTS broker_stream_type")
