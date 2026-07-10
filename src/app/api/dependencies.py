from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.repository import AdminRepository
from app.admin.service import AdminService
from app.broker.factory import create_broker_provider
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.execution.repository import ExecutionRepository
from app.execution.service import ExecutionService
from app.notifications.factory import create_notifier
from app.portfolio.repository import PortfolioRepository
from app.portfolio.service import RebalanceService
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
        notifier=create_notifier(settings),
    )


def get_rebalance_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RebalanceService:
    return RebalanceService(
        PortfolioRepository(session),
        create_broker_provider(settings),
        settings,
        notifier=create_notifier(settings),
    )


def get_execution_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExecutionService:
    return ExecutionService(
        ExecutionRepository(session),
        create_broker_provider(settings),
        settings,
        notifier=create_notifier(settings),
    )
