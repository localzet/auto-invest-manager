from dataclasses import dataclass
from uuid import UUID

from app.models.enums import AccountEventType, ReconciliationStatus


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    reconciliation_id: UUID
    status: ReconciliationStatus
    event_types: tuple[AccountEventType, ...]
    operations_count: int


@dataclass(frozen=True, slots=True)
class DepositClassification:
    event_type: AccountEventType | None
    reason: str


DEPOSIT_OPERATION_TYPES = frozenset(
    {
        "OPERATION_TYPE_INPUT",
        "OPERATION_TYPE_INPUT_ACQUIRING",
        "OPERATION_TYPE_INP_MULTI",
        "OPERATION_TYPE_INPUT_SWIFT",
    }
)
WITHDRAWAL_OPERATION_TYPES = frozenset(
    {
        "OPERATION_TYPE_OUTPUT",
        "OPERATION_TYPE_OUTPUT_ACQUIRING",
        "OPERATION_TYPE_OUT_MULTI",
        "OPERATION_TYPE_OUTPUT_SWIFT",
    }
)


def classify_operation(operation_type: str, state: str) -> DepositClassification:
    if state not in {"OPERATION_STATE_EXECUTED", "EXECUTED"}:
        return DepositClassification(None, "operation_not_executed")
    if operation_type in DEPOSIT_OPERATION_TYPES:
        return DepositClassification(AccountEventType.DEPOSIT_DETECTED, "external_cash_input")
    if operation_type in WITHDRAWAL_OPERATION_TYPES:
        return DepositClassification(AccountEventType.WITHDRAWAL_DETECTED, "external_cash_output")
    return DepositClassification(None, "not_external_cash_operation")
