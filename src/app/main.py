from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Auto Invest Manager API",
        version="0.1.0",
        debug=settings.app_debug,
    )
    application.include_router(health_router)
    return application


app = create_app()
