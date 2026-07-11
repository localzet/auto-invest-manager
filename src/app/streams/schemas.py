from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


def mask_account_id(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"***{value[-4:]}"


class StreamEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    target: str
    stream_type: str
    event_kind: str
    broker_event_time: datetime | None
    received_at: datetime
    source_event_id: str | None
    payload: dict[str, Any]
    processing_status: str
    processing_attempts: int
    processed_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    account_id: str = Field(exclude=True)

    @computed_field
    @property
    def masked_account_id(self) -> str:
        return mask_account_id(self.account_id)


class AccountEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    operation_type: str | None
    amount: Any
    currency: str | None
    occurred_at: datetime
    correlation_id: str
    metadata: dict[str, Any] = Field(validation_alias="event_metadata")
    account_id: str = Field(exclude=True)

    @computed_field
    @property
    def masked_account_id(self) -> str:
        return mask_account_id(self.account_id)


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    reasons: list[str]
    correlation_id: str
    started_at: datetime | None
    finished_at: datetime | None
    operations_count: int
    account_events_count: int
    automation_run_id: UUID | None
    error_code: str | None
    error_message: str | None
    account_id: str = Field(exclude=True)

    @computed_field
    @property
    def masked_account_id(self) -> str:
        return mask_account_id(self.account_id)


class StreamUnitStatus(BaseModel):
    status: str
    connected_at: datetime | None = None
    last_message_at: datetime | None = None
    last_ping_at: datetime | None = None
    last_event_at: datetime | None = None
    reconnect_count: int = 0


class StreamsStatusResponse(BaseModel):
    status: str
    enabled: bool
    provider: str
    target: str
    listener: str
    streams: dict[str, StreamUnitStatus]
    pending_events: int
    dead_letter_events: int
