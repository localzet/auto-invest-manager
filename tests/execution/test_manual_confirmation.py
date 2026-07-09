from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from app.broker.interface import BrokerProvider
from app.broker.mock import MockBrokerProvider
from app.broker.tinvest import TInvestClient
from app.core.config import Settings
from app.execution.repository import initial_order_status
from app.execution.service import ExecutionService
from app.models.enums import PlannedOrderStatus, TradeMode


def test_manual_orders_start_waiting_and_real_transport_does_not_exist() -> None:
    assert (
        initial_order_status(TradeMode.REAL_MANUAL_CONFIRM)
        is PlannedOrderStatus.WAITING_CONFIRMATION
    )
    assert not hasattr(BrokerProvider, "post_real_order")
    assert not hasattr(TInvestClient, "post_real_order")


async def test_admin_can_approve_waiting_manual_order() -> None:
    order = SimpleNamespace(
        id=UUID(int=1),
        status=PlannedOrderStatus.WAITING_CONFIRMATION,
        trade_mode=TradeMode.REAL_MANUAL_CONFIRM,
    )
    approved = SimpleNamespace(status=PlannedOrderStatus.APPROVED)
    repository = SimpleNamespace(
        get_order=AsyncMock(return_value=order),
        get_settings=AsyncMock(
            return_value=SimpleNamespace(trade_mode=TradeMode.REAL_MANUAL_CONFIRM)
        ),
        set_confirmation_status=AsyncMock(return_value=approved),
    )
    service = ExecutionService(repository, MockBrokerProvider(), Settings(_env_file=None))

    result = await service.approve(order.id)

    assert result is approved
    repository.set_confirmation_status.assert_awaited_once_with(order, PlannedOrderStatus.APPROVED)
