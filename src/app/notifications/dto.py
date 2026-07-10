from dataclasses import dataclass
from enum import StrEnum


class NotificationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class Notification:
    title: str
    message: str
    severity: NotificationSeverity = NotificationSeverity.INFO
