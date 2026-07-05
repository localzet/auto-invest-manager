from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.repository import AdminRepository
from app.admin.service import AdminService
from app.broker.factory import create_broker_provider
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.signals.repository import SignalRepository
from app.signals.service import SignalAnalysisService


def get_admin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminService:
    return AdminService(AdminRepository(session), create_broker_provider(settings), settings)


def get_signal_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SignalAnalysisService:
    return SignalAnalysisService(
        SignalRepository(session),
        create_broker_provider(settings),
    )
