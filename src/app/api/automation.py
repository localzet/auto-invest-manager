from typing import Annotated
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_admin_api_key
from app.automation.repository import AutomationRepository
from app.automation.schemas import AutomationRunResponse, AutomationStatusResponse
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.models.enums import AutomationRunStatus, AutomationTrigger

router = APIRouter(
    prefix="/api/v1/admin/automation",
    tags=["automation"],
    dependencies=[Depends(require_admin_api_key)],
)
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("/runs", response_model=list[AutomationRunResponse])
async def list_runs(session: SessionDependency) -> list[AutomationRunResponse]:
    runs = await AutomationRepository(session).list_runs()
    return [AutomationRunResponse.model_validate(run) for run in runs]


@router.get("/runs/{run_id}", response_model=AutomationRunResponse)
async def get_run(run_id: UUID, session: SessionDependency) -> AutomationRunResponse:
    run = await AutomationRepository(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Automation run not found")
    return AutomationRunResponse.model_validate(run)


@router.post("/run", response_model=AutomationRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_manual_run(
    session: SessionDependency,
    settings: SettingsDependency,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=96,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ] = None,
) -> AutomationRunResponse:
    system = await AutomationRepository(session).get_settings()
    if system is None:
        raise HTTPException(status_code=409, detail="System settings are not seeded")
    correlation_id = f"manual:{idempotency_key or uuid4().hex}"
    repository = AutomationRepository(session)
    run, created = await repository.create(
        AutomationTrigger.MANUAL,
        correlation_id,
        system.trade_mode,
        "admin",
    )
    if created:
        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            try:
                await redis.enqueue_job(
                    "run_automation_cycle",
                    correlation_id,
                    AutomationTrigger.MANUAL.value,
                    "admin",
                    str(run.id),
                    _job_id=f"automation:{run.id}",
                )
            finally:
                await redis.aclose()
        except Exception as error:
            await repository.finish(
                run,
                AutomationRunStatus.FAILED,
                "admin",
                reason="Automation queue is unavailable",
                error_code="queue_unavailable",
                error_message=f"Queue unavailable ({type(error).__name__})",
            )
            raise HTTPException(status_code=503, detail="Automation queue is unavailable") from None
    return AutomationRunResponse.model_validate(run)


@router.get("/status", response_model=AutomationStatusResponse)
async def automation_status(
    session: SessionDependency, settings: SettingsDependency
) -> AutomationStatusResponse:
    repository = AutomationRepository(session)
    system = await repository.get_settings()
    if system is None:
        raise HTTPException(status_code=409, detail="System settings are not seeded")
    runs = await repository.list_runs(limit=1)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        worker_ok = bool(await redis.exists("automation:worker:health"))
        scheduler_ok = bool(await redis.exists("automation:scheduler:heartbeat"))
    finally:
        await redis.aclose()
    return AutomationStatusResponse(
        scheduler_enabled=settings.automation_scheduler_enabled,
        trade_mode=system.trade_mode,
        kill_switch=system.kill_switch,
        worker_status="ok" if worker_ok else "unavailable",
        scheduler_status="ok" if scheduler_ok else "unavailable",
        running_runs=await repository.running_count(),
        last_run=(AutomationRunResponse.model_validate(runs[0]) if runs else None),
    )
