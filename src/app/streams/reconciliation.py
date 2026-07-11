from datetime import UTC, datetime, timedelta

from app.automation.repository import AutomationRepository
from app.broker.dto import BrokerOperation, OperationsCursorRequest
from app.broker.interface import BrokerProvider
from app.models.enums import (
    AccountEventType,
    ReconciliationReason,
    ReconciliationStatus,
)
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.interface import Notifier
from app.streams.canonical import fingerprint
from app.streams.dto import ReconciliationResult, classify_operation
from app.streams.repository import StreamRepository


class AccountReconciliationService:
    def __init__(
        self,
        repository: StreamRepository,
        automation_repository: AutomationRepository,
        broker: BrokerProvider,
        notifier: Notifier,
        provider: str,
        target: str,
        operations_lookback_hours: int,
        max_pages: int,
        is_sandbox: bool,
    ) -> None:
        self._repository = repository
        self._automation_repository = automation_repository
        self._broker = broker
        self._notifier = notifier
        self._provider = provider
        self._target = target
        self._lookback_hours = operations_lookback_hours
        self._max_pages = max_pages
        self._is_sandbox = is_sandbox

    async def reconcile(
        self,
        account_id: str,
        reasons: set[ReconciliationReason],
        correlation_id: str,
    ) -> ReconciliationResult:
        value = await self._repository.create_reconciliation(
            account_id, {reason.value for reason in reasons}, correlation_id
        )
        operations: list[BrokerOperation] = []
        created_types: list[AccountEventType] = []
        try:
            accounts = await self._broker.get_accounts()
            account = next((item for item in accounts if item.account_id == account_id), None)
            if account is None:
                raise ValueError("Broker account not found")
            await self._broker.get_positions(account_id)
            portfolio = await self._broker.get_portfolio(account_id)
            operations, cursor_value, cursor = await self._read_operations(account_id)
            await self._automation_repository.save_broker_state(
                account, portfolio, self._is_sandbox
            )
            for operation in operations:
                event_type = self._operation_event_type(operation)
                if event_type is None:
                    continue
                event_fingerprint = fingerprint(
                    self._provider,
                    self._target,
                    account_id,
                    operation.operation_id,
                    event_type.value,
                )
                _, created = await self._repository.save_account_event(
                    value,
                    event_type,
                    operation,
                    event_fingerprint,
                    {
                        "reason": classify_operation(
                            operation.operation_type, operation.state
                        ).reason
                    },
                )
                if created:
                    created_types.append(event_type)
                    await self._audit_event(value.id, event_type)
                    if event_type is AccountEventType.DEPOSIT_DETECTED:
                        await self._notifier.send(
                            Notification(
                                "Подтверждено внешнее пополнение",
                                f"Сумма: {operation.payment.amount} {operation.payment.currency}.",
                                NotificationSeverity.INFO,
                            )
                        )
            if not created_types and reasons:
                _, created = await self._repository.save_account_event(
                    value,
                    AccountEventType.ACCOUNT_CHANGE,
                    None,
                    fingerprint(account_id, correlation_id, "ACCOUNT_CHANGE"),
                    {"reasons": sorted(reason.value for reason in reasons)},
                )
                if created:
                    created_types.append(AccountEventType.ACCOUNT_CHANGE)
                    await self._audit_event(value.id, AccountEventType.ACCOUNT_CHANGE)
            await self._repository.commit_cursor(cursor, cursor_value, operations)
            await self._repository.finish_reconciliation(
                value,
                ReconciliationStatus.SUCCEEDED,
                len(operations),
                len(created_types),
            )
            return ReconciliationResult(
                value.id,
                ReconciliationStatus.SUCCEEDED,
                tuple(created_types),
                len(operations),
            )
        except Exception as error:
            await self._repository.rollback()
            safe_message = f"Account reconciliation failed ({type(error).__name__})"
            await self._repository.finish_reconciliation(
                value,
                ReconciliationStatus.FAILED,
                len(operations),
                0,
                error_code="reconciliation_failed",
                error_message=safe_message,
            )
            await self._notifier.send(
                Notification(
                    "Account reconciliation failed",
                    safe_message,
                    NotificationSeverity.CRITICAL,
                )
            )
            return ReconciliationResult(value.id, ReconciliationStatus.FAILED, (), len(operations))

    async def _read_operations(
        self, account_id: str
    ) -> tuple[list[BrokerOperation], str | None, object]:
        cursor = await self._repository.get_cursor(account_id, self._provider, self._target)
        current = cursor.cursor
        operations: list[BrokerOperation] = []
        from_ = cursor.last_operation_time or (
            datetime.now(UTC) - timedelta(hours=self._lookback_hours)
        )
        for _ in range(self._max_pages):
            page = await self._broker.get_operations_page(
                OperationsCursorRequest(
                    account_id=account_id,
                    from_=from_,
                    to=datetime.now(UTC),
                    cursor=current,
                )
            )
            operations.extend(page.items)
            current = page.next_cursor
            if not page.has_next:
                return operations, current, cursor
        raise RuntimeError("Operations pagination limit exceeded")

    @staticmethod
    def _operation_event_type(operation: BrokerOperation) -> AccountEventType | None:
        classification = classify_operation(operation.operation_type, operation.state)
        if classification.event_type is not None:
            return classification.event_type
        if operation.state in {
            "OPERATION_STATE_EXECUTED",
            "EXECUTED",
        } and operation.operation_type in {
            "OPERATION_TYPE_BUY",
            "OPERATION_TYPE_SELL",
        }:
            return AccountEventType.ORDER_EXECUTION_DETECTED
        return None

    async def _audit_event(self, reconciliation_id: object, event_type: AccountEventType) -> None:
        event_name = {
            AccountEventType.ACCOUNT_CHANGE: "account.change.detected",
            AccountEventType.DEPOSIT_DETECTED: "account.deposit.detected",
            AccountEventType.WITHDRAWAL_DETECTED: "account.withdrawal.detected",
            AccountEventType.ORDER_EXECUTION_DETECTED: "account.order_execution.detected",
        }[event_type]
        await self._repository.add_audit(
            event_name,
            "reconciliation-worker",
            f"{event_type.value} confirmed by unary reconciliation",
            {"reconciliation_id": str(reconciliation_id)},
        )
