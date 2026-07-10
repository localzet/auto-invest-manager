from dataclasses import dataclass
from uuid import UUID

from app.models.enums import AutomationRunStatus, AutomationTrigger


@dataclass(frozen=True, slots=True)
class AutomationCycleRequest:
    trigger: AutomationTrigger
    correlation_id: str
    actor: str
    run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AutomationCycleResult:
    run_id: UUID
    status: AutomationRunStatus
    reason: str | None = None
