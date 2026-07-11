import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import engine, get_session
from app.models.entities import AutomationRun
from app.models.enums import AutomationRunStatus
from app.streams.schemas import StreamsStatusResponse

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None


class WorkerHealthResponse(BaseModel):
    status: str
    scheduler_enabled: bool
    redis: str
    worker: str
    last_run_status: str | None
    last_run_finished_at: datetime | None
    running_runs: int


def get_engine() -> AsyncEngine:
    return engine


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def readiness(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    database: Annotated[AsyncEngine, Depends(get_engine)],
) -> HealthResponse:
    checks: dict[str, str] = {}

    try:
        async with asyncio.timeout(settings.readiness_timeout_seconds):
            async with database.connect() as connection:
                await connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with asyncio.timeout(settings.readiness_timeout_seconds):
            await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    finally:
        await redis.aclose()

    if "error" in checks.values():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable", checks=checks)
    return HealthResponse(status="ok", checks=checks)


@router.get("/worker", response_model=WorkerHealthResponse)
async def worker_health(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkerHealthResponse:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    redis_status = "ok"
    worker_status = "unavailable"
    try:
        await redis.ping()
        worker_status = "ok" if await redis.exists("automation:worker:health") else "unavailable"
    except Exception:
        redis_status = "error"
    finally:
        await redis.aclose()
    last_run = await session.scalar(
        select(AutomationRun).order_by(AutomationRun.created_at.desc()).limit(1)
    )
    running = int(
        await session.scalar(
            select(func.count(AutomationRun.id)).where(
                AutomationRun.status == AutomationRunStatus.RUNNING
            )
        )
        or 0
    )
    overall = "ok" if redis_status == "ok" and worker_status == "ok" else "unavailable"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return WorkerHealthResponse(
        status=overall,
        scheduler_enabled=settings.automation_scheduler_enabled,
        redis=redis_status,
        worker=worker_status,
        last_run_status=last_run.status.value if last_run else None,
        last_run_finished_at=last_run.finished_at if last_run else None,
        running_runs=running,
    )


@router.get("/streams", response_model=StreamsStatusResponse)
async def stream_health(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamsStatusResponse:
    from app.api.streams import _status

    return await _status(session, settings)
