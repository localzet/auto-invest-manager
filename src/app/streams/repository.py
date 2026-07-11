from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.dto import BrokerOperation, BrokerStreamEvent
from app.models.entities import (
    AccountEvent,
    AccountReconciliation,
    AuditLog,
    BrokerOperationCursor,
    BrokerStreamEventRecord,
    BrokerStreamState,
    ExecutionOrder,
    OrderEvent,
)
from app.models.enums import (
    AccountEventType,
    BrokerStreamEventKind,
    BrokerStreamStatus,
    BrokerStreamType,
    ReconciliationStatus,
    StreamEventProcessingStatus,
)
from app.streams.canonical import event_dedupe_key, sanitize_payload


class StreamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rollback(self) -> None:
        await self._session.rollback()

    async def persist_event(
        self, event: BrokerStreamEvent, correlation_id: str
    ) -> tuple[BrokerStreamEventRecord, bool]:
        dedupe_key = event_dedupe_key(event)
        existing = await self._session.scalar(
            select(BrokerStreamEventRecord).where(BrokerStreamEventRecord.dedupe_key == dedupe_key)
        )
        if existing is not None:
            await self.add_audit(
                "broker.event.duplicate",
                "stream-listener",
                "Duplicate broker stream event ignored",
                {"event_id": str(existing.id)},
            )
            return existing, False
        record = BrokerStreamEventRecord(
            provider=event.provider,
            target=event.target,
            stream_type=BrokerStreamType(event.stream_type),
            event_kind=BrokerStreamEventKind(event.event_kind),
            account_id=event.account_id,
            broker_event_time=event.broker_event_time,
            received_at=event.received_at,
            source_event_id=event.source_event_id,
            dedupe_key=dedupe_key,
            payload=sanitize_payload(event.payload),
            processing_status=StreamEventProcessingStatus.PENDING,
            correlation_id=correlation_id,
        )
        self._session.add(record)
        self._session.add(
            AuditLog(
                event_type="broker.event.received",
                actor="stream-listener",
                message="Broker stream event persisted",
                context={"stream_type": event.stream_type, "event_kind": event.event_kind},
            )
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._session.scalar(
                select(BrokerStreamEventRecord).where(
                    BrokerStreamEventRecord.dedupe_key == dedupe_key
                )
            )
            if existing is None:
                raise
            return existing, False
        return record, True

    async def claim_event(
        self, event_id: UUID, max_attempts: int
    ) -> BrokerStreamEventRecord | None:
        event = await self._session.scalar(
            select(BrokerStreamEventRecord)
            .where(
                BrokerStreamEventRecord.id == event_id,
                BrokerStreamEventRecord.processing_status.in_(
                    [
                        StreamEventProcessingStatus.PENDING,
                        StreamEventProcessingStatus.FAILED,
                    ]
                ),
                BrokerStreamEventRecord.processing_attempts < max_attempts,
            )
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return None
        event.processing_status = StreamEventProcessingStatus.PROCESSING
        event.processing_attempts += 1
        await self._session.commit()
        return event

    async def complete_event(self, event: BrokerStreamEventRecord, ignored: bool = False) -> None:
        event.processing_status = (
            StreamEventProcessingStatus.IGNORED
            if ignored
            else StreamEventProcessingStatus.PROCESSED
        )
        event.processed_at = datetime.now(UTC)
        event.error_code = None
        event.error_message = None
        self._session.add(
            AuditLog(
                event_type="broker.event.processed",
                actor="event-processor",
                message="Broker stream event processed",
                context={"event_id": str(event.id), "ignored": ignored},
            )
        )
        await self._session.commit()

    async def fail_event(
        self,
        event: BrokerStreamEventRecord,
        max_attempts: int,
        error_code: str,
        safe_message: str,
    ) -> bool:
        dead_letter = event.processing_attempts >= max_attempts
        event.processing_status = (
            StreamEventProcessingStatus.DEAD_LETTER
            if dead_letter
            else StreamEventProcessingStatus.FAILED
        )
        event.error_code = error_code
        event.error_message = safe_message
        self._session.add(
            AuditLog(
                event_type=("broker.event.dead_letter" if dead_letter else "broker.event.failed"),
                severity="warning",
                actor="event-processor",
                message=safe_message,
                context={"event_id": str(event.id)},
            )
        )
        await self._session.commit()
        return dead_letter

    async def retry_event(self, event: BrokerStreamEventRecord) -> None:
        event.processing_status = StreamEventProcessingStatus.PENDING
        event.error_code = None
        event.error_message = None
        event.next_attempt_at = None
        self._session.add(
            AuditLog(
                event_type="broker.event.retried",
                actor="admin",
                message="Dead-letter event scheduled for retry",
                context={"event_id": str(event.id)},
            )
        )
        await self._session.commit()

    async def get_event(self, event_id: UUID) -> BrokerStreamEventRecord | None:
        return await self._session.get(BrokerStreamEventRecord, event_id)

    async def record_trade_signal(self, event: BrokerStreamEventRecord) -> None:
        order_id = str(event.payload.get("order_id", ""))
        execution = await self._session.scalar(
            select(ExecutionOrder).where(ExecutionOrder.broker_order_id == order_id)
        )
        if execution is None:
            return
        self._session.add(
            OrderEvent(
                execution_order_id=execution.id,
                event_type="TRADE_STREAM_SIGNAL",
                broker_status="STREAM_REPORTED",
                payload=sanitize_payload(event.payload),
            )
        )
        await self._session.commit()

    async def list_events(self, limit: int = 100, offset: int = 0) -> list[BrokerStreamEventRecord]:
        result = await self._session.scalars(
            select(BrokerStreamEventRecord)
            .order_by(BrokerStreamEventRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def upsert_state(
        self,
        provider: str,
        target: str,
        stream_type: BrokerStreamType,
        account_set_hash: str,
        instance_id: str,
        status: BrokerStreamStatus | None,
        **values: Any,
    ) -> BrokerStreamState:
        state = await self._session.scalar(
            select(BrokerStreamState).where(
                BrokerStreamState.provider == provider,
                BrokerStreamState.target == target,
                BrokerStreamState.stream_type == stream_type,
                BrokerStreamState.account_set_hash == account_set_hash,
            )
        )
        if state is None:
            state = BrokerStreamState(
                provider=provider,
                target=target,
                stream_type=stream_type,
                account_set_hash=account_set_hash,
                instance_id=instance_id,
                status=status or BrokerStreamStatus.STARTING,
                subscription_status={},
            )
            self._session.add(state)
        state.instance_id = instance_id
        if status is not None:
            state.status = status
        for key, value in values.items():
            setattr(state, key, value)
        await self._session.commit()
        return state

    async def list_states(self) -> list[BrokerStreamState]:
        return list((await self._session.scalars(select(BrokerStreamState))).all())

    async def get_cursor(
        self, account_id: str, provider: str, target: str
    ) -> BrokerOperationCursor:
        cursor = await self._session.scalar(
            select(BrokerOperationCursor).where(
                BrokerOperationCursor.account_id == account_id,
                BrokerOperationCursor.provider == provider,
                BrokerOperationCursor.target == target,
            )
        )
        if cursor is None:
            cursor = BrokerOperationCursor(
                account_id=account_id,
                provider=provider,
                target=target,
            )
            self._session.add(cursor)
            await self._session.flush()
        return cursor

    async def commit_cursor(
        self,
        cursor: BrokerOperationCursor,
        next_cursor: str | None,
        operations: list[BrokerOperation],
    ) -> None:
        cursor.cursor = next_cursor
        cursor.last_successful_sync_at = datetime.now(UTC)
        if operations:
            cursor.last_operation_time = max(item.date for item in operations)
            cursor.last_operation_fingerprint = operations[-1].operation_id
        await self._session.commit()

    async def create_reconciliation(
        self, account_id: str, reasons: set[str], correlation_id: str
    ) -> AccountReconciliation:
        existing = await self._session.scalar(
            select(AccountReconciliation).where(
                AccountReconciliation.correlation_id == correlation_id
            )
        )
        if existing is not None:
            return existing
        value = AccountReconciliation(
            account_id=account_id,
            status=ReconciliationStatus.RUNNING,
            reasons=sorted(reasons),
            correlation_id=correlation_id,
            started_at=datetime.now(UTC),
        )
        self._session.add(value)
        self._session.add(
            AuditLog(
                event_type="account.reconciliation.started",
                actor="reconciliation-worker",
                message="Account reconciliation started",
                context={"reconciliation_id": correlation_id},
            )
        )
        await self._session.commit()
        return value

    async def save_account_event(
        self,
        reconciliation: AccountReconciliation,
        event_type: AccountEventType,
        operation: BrokerOperation | None,
        fingerprint: str,
        metadata: dict[str, Any],
    ) -> tuple[AccountEvent, bool]:
        existing = await self._session.scalar(
            select(AccountEvent).where(AccountEvent.fingerprint == fingerprint)
        )
        if existing is not None:
            return existing, False
        event = AccountEvent(
            account_id=reconciliation.account_id,
            event_type=event_type,
            operation_id=operation.operation_id if operation else None,
            operation_type=operation.operation_type if operation else None,
            amount=operation.payment.amount if operation else None,
            currency=operation.payment.currency if operation else None,
            occurred_at=operation.date if operation else datetime.now(UTC),
            fingerprint=fingerprint,
            correlation_id=reconciliation.correlation_id,
            event_metadata=metadata,
        )
        self._session.add(event)
        await self._session.flush()
        return event, True

    async def finish_reconciliation(
        self,
        value: AccountReconciliation,
        status: ReconciliationStatus,
        operations_count: int,
        events_count: int,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        value.status = status
        value.finished_at = datetime.now(UTC)
        value.operations_count = operations_count
        value.account_events_count = events_count
        value.error_code = error_code
        value.error_message = error_message
        self._session.add(
            AuditLog(
                event_type=(
                    "account.reconciliation.succeeded"
                    if status is ReconciliationStatus.SUCCEEDED
                    else "account.reconciliation.failed"
                ),
                severity="info" if status is ReconciliationStatus.SUCCEEDED else "warning",
                actor="reconciliation-worker",
                message=f"Account reconciliation {status.value.lower()}",
                context={"reconciliation_id": str(value.id)},
            )
        )
        await self._session.commit()

    async def list_account_events(self, limit: int = 100, offset: int = 0) -> list[AccountEvent]:
        return list(
            (
                await self._session.scalars(
                    select(AccountEvent)
                    .order_by(AccountEvent.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )

    async def get_account_event(self, event_id: UUID) -> AccountEvent | None:
        return await self._session.get(AccountEvent, event_id)

    async def list_reconciliations(
        self, limit: int = 100, offset: int = 0
    ) -> list[AccountReconciliation]:
        return list(
            (
                await self._session.scalars(
                    select(AccountReconciliation)
                    .order_by(AccountReconciliation.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )

    async def get_reconciliation(self, reconciliation_id: UUID) -> AccountReconciliation | None:
        return await self._session.get(AccountReconciliation, reconciliation_id)

    async def counts(self) -> tuple[int, int]:
        pending = int(
            await self._session.scalar(
                select(func.count(BrokerStreamEventRecord.id)).where(
                    BrokerStreamEventRecord.processing_status.in_(
                        [
                            StreamEventProcessingStatus.PENDING,
                            StreamEventProcessingStatus.PROCESSING,
                            StreamEventProcessingStatus.FAILED,
                        ]
                    )
                )
            )
            or 0
        )
        dead = int(
            await self._session.scalar(
                select(func.count(BrokerStreamEventRecord.id)).where(
                    BrokerStreamEventRecord.processing_status
                    == StreamEventProcessingStatus.DEAD_LETTER
                )
            )
            or 0
        )
        return pending, dead

    async def cleanup(self, before: datetime, batch_size: int = 1000) -> int:
        ids = list(
            (
                await self._session.scalars(
                    select(BrokerStreamEventRecord.id)
                    .where(
                        BrokerStreamEventRecord.processing_status.in_(
                            [
                                StreamEventProcessingStatus.PROCESSED,
                                StreamEventProcessingStatus.IGNORED,
                            ]
                        ),
                        BrokerStreamEventRecord.processed_at < before,
                    )
                    .limit(batch_size)
                )
            ).all()
        )
        if ids:
            await self._session.execute(
                delete(BrokerStreamEventRecord).where(BrokerStreamEventRecord.id.in_(ids))
            )
            await self._session.commit()
        return len(ids)

    async def startup_recovery(self) -> tuple[int, int]:
        processing = list(
            (
                await self._session.scalars(
                    select(BrokerStreamEventRecord).where(
                        BrokerStreamEventRecord.processing_status
                        == StreamEventProcessingStatus.PROCESSING
                    )
                )
            ).all()
        )
        states = list(
            (
                await self._session.scalars(
                    select(BrokerStreamState).where(
                        BrokerStreamState.status == BrokerStreamStatus.CONNECTED
                    )
                )
            ).all()
        )
        for event in processing:
            event.processing_status = StreamEventProcessingStatus.PENDING
        for state in states:
            state.status = BrokerStreamStatus.STOPPED
            state.disconnected_at = datetime.now(UTC)
        await self._session.commit()
        return len(processing), len(states)

    async def pending_event_ids(self) -> list[UUID]:
        return list(
            (
                await self._session.scalars(
                    select(BrokerStreamEventRecord.id).where(
                        BrokerStreamEventRecord.processing_status
                        == StreamEventProcessingStatus.PENDING
                    )
                )
            ).all()
        )

    async def add_audit(
        self, event_type: str, actor: str, message: str, context: dict[str, Any]
    ) -> None:
        self._session.add(
            AuditLog(
                event_type=event_type,
                actor=actor,
                message=message,
                context=context,
            )
        )
        await self._session.commit()
