from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.admin.errors import ResourceConflictError, ResourceNotFoundError
from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.execution.errors import RiskRejectedError


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Auto Invest Manager API",
        version="0.1.0",
        debug=settings.app_debug,
    )
    application.include_router(health_router)
    application.include_router(admin_router)

    @application.exception_handler(ResourceNotFoundError)
    async def handle_not_found(_: Request, error: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @application.exception_handler(ResourceConflictError)
    async def handle_conflict(_: Request, error: ResourceConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(RiskRejectedError)
    async def handle_risk_rejected(_: Request, error: RiskRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Risk check rejected order", "reasons": error.reasons},
        )

    return application


app = create_app()
