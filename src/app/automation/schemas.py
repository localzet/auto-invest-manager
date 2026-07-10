from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AutomationRunStatus,
    AutomationStep,
    AutomationTrigger,
    TradeMode,
)


class AutomationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger: AutomationTrigger
    status: AutomationRunStatus
    trade_mode: TradeMode
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    current_step: AutomationStep
    signals_count: int
    rebalance_plan_id: UUID | None
    planned_orders_count: int
    executed_orders_count: int
    virtual_trades_count: int
    error_code: str | None
    error_message: str | None
    metadata: dict[str, Any] = Field(validation_alias="run_metadata")
    created_at: datetime
    updated_at: datetime


class AutomationStatusResponse(BaseModel):
    scheduler_enabled: bool
    trade_mode: TradeMode
    kill_switch: bool
    worker_status: str
    scheduler_status: str
    running_runs: int
    last_run: AutomationRunResponse | None
