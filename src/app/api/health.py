import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None


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
