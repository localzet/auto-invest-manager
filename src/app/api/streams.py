from typing import Annotated
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_admin_api_key
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import ReconciliationReason, StreamEventProcessingStatus
from app.streams.processor import schedule_debounced_reconciliation
from app.streams.repository import StreamRepository
from app.streams.schemas import (
    AccountEventResponse,
    ReconciliationResponse,
    StreamEventResponse,
    StreamsStatusResponse,
    StreamUnitStatus,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["streams"],
    dependencies=[Depends(require_admin_api_key)],
)
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def _status(session: AsyncSession, settings: Settings) -> StreamsStatusResponse:
    repository = StreamRepository(session)
    states = await repository.list_states()
    pending, dead = await repository.counts()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        listener = "ok" if await redis.exists("broker-stream:listener:heartbeat") else "unavailable"
    finally:
        await redis.aclose()
    units: dict[str, StreamUnitStatus] = {}
    for name in ("portfolio", "positions", "trades"):
        state = next((item for item in states if item.stream_type.value.lower() == name), None)
        units[name] = StreamUnitStatus(
            status=(
                state.status.value
                if state
                else ("DISABLED" if not settings.broker_streams_enabled else "STARTING")
            ),
            connected_at=state.connected_at if state else None,
            last_message_at=state.last_message_at if state else None,
            last_ping_at=state.last_ping_at if state else None,
            last_event_at=state.last_event_at if state else None,
            reconnect_count=state.reconnect_count if state else 0,
        )
    statuses = {item.status for item in units.values()}
    overall = (
        "disabled"
        if not settings.broker_streams_enabled
        else "failed"
        if "FAILED" in statuses
        else "degraded"
        if statuses & {"DEGRADED", "RECONNECTING", "STOPPED"}
        else "ok"
    )
    return StreamsStatusResponse(
        status=overall,
        enabled=settings.broker_streams_enabled,
        provider=settings.broker_provider,
        target=settings.tinvest_target,
        listener=listener,
        streams=units,
        pending_events=pending,
        dead_letter_events=dead,
    )


@router.get("/streams/status", response_model=StreamsStatusResponse)
async def streams_status(
    session: SessionDependency, settings: SettingsDependency
) -> StreamsStatusResponse:
    return await _status(session, settings)


@router.get("/streams/events", response_model=list[StreamEventResponse])
async def stream_events(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StreamEventResponse]:
    return [
        StreamEventResponse.model_validate(item)
        for item in await StreamRepository(session).list_events(limit, offset)
    ]


@router.get("/streams/events/{event_id}", response_model=StreamEventResponse)
async def stream_event(event_id: UUID, session: SessionDependency) -> StreamEventResponse:
    value = await StreamRepository(session).get_event(event_id)
    if value is None:
        raise HTTPException(404, "Stream event not found")
    return StreamEventResponse.model_validate(value)


@router.post("/streams/events/{event_id}/retry", response_model=StreamEventResponse)
async def retry_stream_event(
    event_id: UUID, session: SessionDependency, settings: SettingsDependency
) -> StreamEventResponse:
    repository = StreamRepository(session)
    value = await repository.get_event(event_id)
    if value is None:
        raise HTTPException(404, "Stream event not found")
    if value.processing_status is not StreamEventProcessingStatus.DEAD_LETTER:
        raise HTTPException(409, "Only dead-letter events can be retried")
    await repository.retry_event(value)
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await redis.enqueue_job(
            "process_broker_stream_event",
            str(value.id),
            _job_id=f"stream-event-retry:{value.id}:{value.processing_attempts}",
        )
    finally:
        await redis.aclose()
    return StreamEventResponse.model_validate(value)


@router.get("/account-events", response_model=list[AccountEventResponse])
async def account_events(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountEventResponse]:
    return [
        AccountEventResponse.model_validate(item)
        for item in await StreamRepository(session).list_account_events(limit, offset)
    ]


@router.get("/account-events/{event_id}", response_model=AccountEventResponse)
async def account_event(event_id: UUID, session: SessionDependency) -> AccountEventResponse:
    value = await StreamRepository(session).get_account_event(event_id)
    if value is None:
        raise HTTPException(404, "Account event not found")
    return AccountEventResponse.model_validate(value)


@router.post("/accounts/{account_id}/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile_account(account_id: str, settings: SettingsDependency) -> dict[str, str]:
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        key = await schedule_debounced_reconciliation(
            redis,
            account_id,
            ReconciliationReason.MANUAL,
            1,
            settings.account_event_max_debounce_seconds,
        )
    finally:
        await redis.aclose()
    return {"status": "queued", "debounce_key": key}


@router.get("/reconciliations", response_model=list[ReconciliationResponse])
async def reconciliations(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReconciliationResponse]:
    return [
        ReconciliationResponse.model_validate(item)
        for item in await StreamRepository(session).list_reconciliations(limit, offset)
    ]


@router.get("/reconciliations/{reconciliation_id}", response_model=ReconciliationResponse)
async def reconciliation(
    reconciliation_id: UUID, session: SessionDependency
) -> ReconciliationResponse:
    value = await StreamRepository(session).get_reconciliation(reconciliation_id)
    if value is None:
        raise HTTPException(404, "Reconciliation not found")
    return ReconciliationResponse.model_validate(value)
