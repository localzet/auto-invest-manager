from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.broker.dto import SandboxOrderResult
from app.execution.dto import PlannedOrderData
from app.models.entities import (
    AuditLog,
    ExecutionOrder,
    OrderEvent,
    PlannedOrder,
    RebalancePlan,
    RiskProfile,
    SystemSettings,
    TargetAllocation,
    VirtualTrade,
    WatchlistItem,
)
from app.models.enums import PlannedOrderStatus, TradeMode


class ExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_plan(self, plan_id: UUID) -> RebalancePlan | None:
        return await self._session.scalar(
            select(RebalancePlan)
            .where(RebalancePlan.id == plan_id)
            .options(joinedload(RebalancePlan.allocations).joinedload(TargetAllocation.instrument))
        )

    async def get_settings(self) -> SystemSettings | None:
        return await self._session.scalar(select(SystemSettings).limit(1))

    async def get_risk_profile(self) -> RiskProfile | None:
        return await self._session.scalar(
            select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
        )

    async def get_watchlist_item(self, instrument_id: UUID) -> WatchlistItem | None:
        return await self._session.scalar(
            select(WatchlistItem).where(WatchlistItem.instrument_id == instrument_id)
        )

    async def save_orders(
        self, plan: RebalancePlan, data: tuple[PlannedOrderData, ...]
    ) -> list[PlannedOrder]:
        existing = {
            order.idempotency_key: order
            for order in (
                await self._session.scalars(
                    select(PlannedOrder)
                    .where(
                        PlannedOrder.idempotency_key.in_([item.idempotency_key for item in data])
                    )
                    .options(joinedload(PlannedOrder.instrument))
                )
            ).all()
        }
        instruments = {
            allocation.instrument.instrument_uid: allocation.instrument
            for allocation in plan.allocations
        }
        orders = []
        for item in data:
            if item.idempotency_key in existing:
                orders.append(existing[item.idempotency_key])
                continue
            instrument = instruments[item.instrument_uid]
            order = PlannedOrder(
                rebalance_plan_id=plan.id,
                instrument_id=instrument.id,
                account_id=plan.source_account_id,
                direction=item.direction,
                lots=item.lots,
                order_type=item.order_type,
                limit_price=item.limit_price,
                reason=item.reason,
                status=PlannedOrderStatus.PLANNED,
                trade_mode=item.trade_mode,
                idempotency_key=item.idempotency_key,
            )
            order.instrument = instrument
            self._session.add(order)
            orders.append(order)
        self._session.add(
            AuditLog(
                event_type="execution_plan.created",
                message="Dry-run execution plan created",
                context={"rebalance_plan_id": str(plan.id), "orders_count": len(orders)},
            )
        )
        await self._session.commit()
        return orders

    async def get_order(self, order_id: UUID) -> PlannedOrder | None:
        return await self._session.scalar(
            select(PlannedOrder)
            .where(PlannedOrder.id == order_id)
            .options(
                joinedload(PlannedOrder.instrument),
                joinedload(PlannedOrder.virtual_trade).joinedload(VirtualTrade.instrument),
            )
        )

    async def count_trades_since(self, since: datetime) -> int:
        virtual_count = int(
            await self._session.scalar(
                select(func.count(VirtualTrade.id)).where(VirtualTrade.executed_at >= since)
            )
            or 0
        )
        execution_count = int(
            await self._session.scalar(
                select(func.count(ExecutionOrder.id)).where(ExecutionOrder.created_at >= since)
            )
            or 0
        )
        return virtual_count + execution_count

    async def latest_trade_time(self, instrument_id: UUID) -> datetime | None:
        virtual_time = await self._session.scalar(
            select(VirtualTrade.executed_at)
            .where(VirtualTrade.instrument_id == instrument_id)
            .order_by(VirtualTrade.executed_at.desc())
            .limit(1)
        )
        execution_time = await self._session.scalar(
            select(ExecutionOrder.created_at)
            .join(PlannedOrder, PlannedOrder.id == ExecutionOrder.planned_order_id)
            .where(PlannedOrder.instrument_id == instrument_id)
            .order_by(ExecutionOrder.created_at.desc())
            .limit(1)
        )
        timestamps = [
            timestamp
            for timestamp in (
                virtual_time,
                execution_time,
            )
            if timestamp is not None
        ]
        return max(timestamps) if timestamps else None

    async def has_duplicate_order(self, order: PlannedOrder) -> bool:
        duplicate = await self._session.scalar(
            select(PlannedOrder.id).where(
                PlannedOrder.id != order.id,
                PlannedOrder.instrument_id == order.instrument_id,
                PlannedOrder.direction == order.direction,
                PlannedOrder.status == PlannedOrderStatus.PLANNED,
            )
        )
        return duplicate is not None

    async def reject(self, order: PlannedOrder, reasons: tuple[str, ...]) -> None:
        order.status = PlannedOrderStatus.RISK_REJECTED
        self._session.add(
            AuditLog(
                event_type="order.risk_rejected",
                severity="warning",
                message="Dry-run order rejected by final risk check",
                context={"order_id": str(order.id), "reasons": list(reasons)},
            )
        )
        await self._session.commit()

    async def simulate(self, order: PlannedOrder) -> VirtualTrade:
        total = order.limit_price * order.instrument.lot * order.lots
        trade = VirtualTrade(
            planned_order_id=order.id,
            instrument_id=order.instrument_id,
            direction=order.direction,
            lots=order.lots,
            price=order.limit_price,
            total_amount=total,
        )
        trade.instrument = order.instrument
        trade.planned_order = order
        order.status = PlannedOrderStatus.SIMULATED
        self._session.add(trade)
        self._session.add(
            AuditLog(
                event_type="order.simulated",
                message="Virtual trade recorded",
                context={"order_id": str(order.id), "total_amount": str(total)},
            )
        )
        await self._session.commit()
        return trade

    async def list_virtual_trades(self, limit: int = 100) -> list[VirtualTrade]:
        result = await self._session.scalars(
            select(VirtualTrade)
            .options(joinedload(VirtualTrade.instrument))
            .order_by(VirtualTrade.executed_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_execution_order(self, planned_order_id: UUID) -> ExecutionOrder | None:
        return await self._session.scalar(
            select(ExecutionOrder)
            .where(ExecutionOrder.planned_order_id == planned_order_id)
            .options(joinedload(ExecutionOrder.planned_order))
        )

    async def save_sandbox_execution(
        self, order: PlannedOrder, result: SandboxOrderResult
    ) -> ExecutionOrder:
        execution = ExecutionOrder(
            planned_order_id=order.id,
            broker_order_id=result.broker_order_id,
            broker_status=result.broker_status,
            lots_requested=result.lots_requested,
            lots_executed=result.lots_executed,
            execution_price=result.execution_price,
            total_amount=result.total_amount,
            trade_mode=TradeMode.SANDBOX,
        )
        execution.planned_order = order
        execution.events.append(
            OrderEvent(
                event_type="ORDER_POSTED",
                broker_status=result.broker_status,
                payload={
                    "broker_order_id": result.broker_order_id,
                    "lots_requested": result.lots_requested,
                    "lots_executed": result.lots_executed,
                },
            )
        )
        order.status = PlannedOrderStatus.SUBMITTED
        self._session.add(execution)
        self._session.add(
            AuditLog(
                event_type="order.sandbox_posted",
                message="Order posted to T-Invest sandbox",
                context={
                    "planned_order_id": str(order.id),
                    "broker_order_id": result.broker_order_id,
                },
            )
        )
        await self._session.commit()
        return execution
