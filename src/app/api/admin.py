from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.admin.schemas import (
    AccountsResponse,
    AnalysisRunResponse,
    ExecutionOrderResponse,
    InstrumentResponse,
    InstrumentSyncRequest,
    PlannedOrderResponse,
    RebalancePlanResponse,
    RiskProfileResponse,
    RiskProfileUpdate,
    SignalResponse,
    StrategyProfileResponse,
    StrategyProfileUpdate,
    SystemSettingsResponse,
    SystemSettingsUpdate,
    VirtualTradeResponse,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistItemUpdate,
)
from app.admin.service import AdminService
from app.api.dependencies import (
    get_admin_service,
    get_execution_service,
    get_rebalance_service,
    get_signal_service,
)
from app.api.security import require_admin_api_key
from app.execution.service import ExecutionService
from app.models.entities import SystemSettings
from app.portfolio.service import RebalanceService
from app.signals.service import SignalAnalysisService

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_api_key)],
)
AdminServiceDependency = Annotated[AdminService, Depends(get_admin_service)]
SignalServiceDependency = Annotated[SignalAnalysisService, Depends(get_signal_service)]
RebalanceServiceDependency = Annotated[RebalanceService, Depends(get_rebalance_service)]
ExecutionServiceDependency = Annotated[ExecutionService, Depends(get_execution_service)]


def _settings_response(
    entity: SystemSettings, real_trading_enabled: bool
) -> SystemSettingsResponse:
    response = SystemSettingsResponse.model_validate(
        {
            "id": entity.id,
            "trade_mode": entity.trade_mode,
            "kill_switch": entity.kill_switch,
            "updated_at": entity.updated_at,
            "real_trading_enabled_by_env": real_trading_enabled,
        }
    )
    return response


@router.get("/accounts", response_model=AccountsResponse)
async def get_accounts(service: AdminServiceDependency) -> AccountsResponse:
    return AccountsResponse(accounts=await service.get_accounts())


@router.get("/settings", response_model=SystemSettingsResponse)
async def get_system_settings(service: AdminServiceDependency) -> SystemSettingsResponse:
    entity = await service.get_system_settings()
    return _settings_response(entity, service.real_trading_enabled_by_env)


@router.patch("/settings", response_model=SystemSettingsResponse)
async def update_system_settings(
    payload: SystemSettingsUpdate, service: AdminServiceDependency
) -> SystemSettingsResponse:
    entity = await service.update_system_settings(payload)
    return _settings_response(entity, service.real_trading_enabled_by_env)


@router.post("/instruments/sync", response_model=list[InstrumentResponse])
async def sync_instruments(
    payload: InstrumentSyncRequest, service: AdminServiceDependency
) -> list[InstrumentResponse]:
    entities = await service.sync_instruments(payload.instruments)
    return [InstrumentResponse.model_validate(entity) for entity in entities]


@router.get("/watchlist", response_model=list[WatchlistItemResponse])
async def get_watchlist(service: AdminServiceDependency) -> list[WatchlistItemResponse]:
    return [WatchlistItemResponse.model_validate(item) for item in await service.list_watchlist()]


@router.post(
    "/watchlist", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_watchlist_item(
    payload: WatchlistItemCreate, service: AdminServiceDependency
) -> WatchlistItemResponse:
    return WatchlistItemResponse.model_validate(await service.add_watchlist_item(payload))


@router.patch("/watchlist/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    item_id: UUID,
    payload: WatchlistItemUpdate,
    service: AdminServiceDependency,
) -> WatchlistItemResponse:
    return WatchlistItemResponse.model_validate(
        await service.update_watchlist_item(item_id, payload)
    )


@router.delete("/watchlist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist_item(item_id: UUID, service: AdminServiceDependency) -> Response:
    await service.remove_watchlist_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/risk-profile", response_model=RiskProfileResponse)
async def get_risk_profile(service: AdminServiceDependency) -> RiskProfileResponse:
    return RiskProfileResponse.model_validate(await service.get_risk_profile())


@router.patch("/risk-profile", response_model=RiskProfileResponse)
async def update_risk_profile(
    payload: RiskProfileUpdate, service: AdminServiceDependency
) -> RiskProfileResponse:
    return RiskProfileResponse.model_validate(await service.update_risk_profile(payload))


@router.get("/strategy-profile", response_model=StrategyProfileResponse)
async def get_strategy_profile(service: AdminServiceDependency) -> StrategyProfileResponse:
    return StrategyProfileResponse.model_validate(await service.get_strategy_profile())


@router.patch("/strategy-profile", response_model=StrategyProfileResponse)
async def update_strategy_profile(
    payload: StrategyProfileUpdate, service: AdminServiceDependency
) -> StrategyProfileResponse:
    return StrategyProfileResponse.model_validate(await service.update_strategy_profile(payload))


@router.get("/signals", response_model=list[SignalResponse])
async def get_latest_signals(
    service: SignalServiceDependency,
) -> list[SignalResponse]:
    return [SignalResponse.model_validate(signal) for signal in await service.latest()]


@router.post("/analysis/run", response_model=AnalysisRunResponse)
async def run_analysis(service: SignalServiceDependency) -> AnalysisRunResponse:
    signals = await service.run()
    return AnalysisRunResponse(
        signals=[SignalResponse.model_validate(signal) for signal in signals]
    )


@router.get("/rebalance-plans", response_model=list[RebalancePlanResponse])
async def get_rebalance_plans(
    service: RebalanceServiceDependency,
) -> list[RebalancePlanResponse]:
    return [RebalancePlanResponse.model_validate(plan) for plan in await service.list_plans()]


@router.post("/rebalance-plans/run", response_model=RebalancePlanResponse)
async def run_rebalance_planning(
    service: RebalanceServiceDependency,
) -> RebalancePlanResponse:
    return RebalancePlanResponse.model_validate(await service.create_plan())


@router.post(
    "/rebalance-plans/{plan_id}/execution-plan",
    response_model=list[PlannedOrderResponse],
)
async def create_execution_plan(
    plan_id: UUID, service: ExecutionServiceDependency
) -> list[PlannedOrderResponse]:
    return [
        PlannedOrderResponse.model_validate(order) for order in await service.plan_orders(plan_id)
    ]


@router.get("/planned-orders", response_model=list[PlannedOrderResponse])
async def get_planned_orders(
    service: ExecutionServiceDependency,
) -> list[PlannedOrderResponse]:
    return [PlannedOrderResponse.model_validate(order) for order in await service.list_orders()]


@router.post("/planned-orders/{order_id}/approve", response_model=PlannedOrderResponse)
async def approve_planned_order(
    order_id: UUID, service: ExecutionServiceDependency
) -> PlannedOrderResponse:
    return PlannedOrderResponse.model_validate(await service.approve(order_id))


@router.post("/planned-orders/{order_id}/reject", response_model=PlannedOrderResponse)
async def reject_planned_order(
    order_id: UUID, service: ExecutionServiceDependency
) -> PlannedOrderResponse:
    return PlannedOrderResponse.model_validate(await service.reject(order_id))


@router.post("/planned-orders/{order_id}/dry-run", response_model=VirtualTradeResponse)
async def execute_dry_run(
    order_id: UUID, service: ExecutionServiceDependency
) -> VirtualTradeResponse:
    return VirtualTradeResponse.model_validate(await service.execute(order_id))


@router.post("/planned-orders/{order_id}/sandbox", response_model=ExecutionOrderResponse)
async def execute_sandbox_order(
    order_id: UUID, service: ExecutionServiceDependency
) -> ExecutionOrderResponse:
    return ExecutionOrderResponse.model_validate(await service.execute_sandbox(order_id))


@router.get("/virtual-trades", response_model=list[VirtualTradeResponse])
async def get_virtual_trades(
    service: ExecutionServiceDependency,
) -> list[VirtualTradeResponse]:
    return [
        VirtualTradeResponse.model_validate(trade) for trade in await service.list_virtual_trades()
    ]
