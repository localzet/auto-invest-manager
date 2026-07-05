from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.execution.dto import PlannedOrderData
from app.models.entities import (
    AuditLog,
    PlannedOrder,
    RebalancePlan,
    RiskProfile,
    SystemSettings,
    TargetAllocation,
    VirtualTrade,
    WatchlistItem,
)
from app.models.enums import PlannedOrderStatus


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

    async def count_virtual_trades_since(self, since: datetime) -> int:
        return int(
            await self._session.scalar(
                select(func.count(VirtualTrade.id)).where(VirtualTrade.executed_at >= since)
            )
            or 0
        )

    async def latest_virtual_trade(self, instrument_id: UUID) -> VirtualTrade | None:
        return await self._session.scalar(
            select(VirtualTrade)
            .where(VirtualTrade.instrument_id == instrument_id)
            .order_by(VirtualTrade.executed_at.desc())
            .limit(1)
        )

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
