from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.entities import (
    AuditLog,
    Instrument,
    RebalancePlan,
    RiskProfile,
    Signal,
    TargetAllocation,
    WatchlistItem,
)
from app.models.enums import RebalancePlanStatus
from app.portfolio.dto import RebalanceResult


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_risk_profile(self) -> RiskProfile | None:
        return await self._session.scalar(
            select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
        )

    async def get_watchlist(self) -> Sequence[WatchlistItem]:
        result = await self._session.scalars(
            select(WatchlistItem)
            .options(joinedload(WatchlistItem.instrument))
            .order_by(WatchlistItem.priority.desc())
        )
        return result.all()

    async def get_latest_signal(self, instrument_id: UUID) -> Signal | None:
        return await self._session.scalar(
            select(Signal)
            .where(Signal.instrument_id == instrument_id)
            .order_by(Signal.calculated_at.desc())
            .limit(1)
        )

    async def save_plan(
        self,
        source_account_id: str,
        portfolio_value: Decimal,
        cash_available: Decimal,
        result: RebalanceResult,
        instruments: dict[str, Instrument],
    ) -> RebalancePlan:
        plan = RebalancePlan(
            source_account_id=source_account_id,
            status=RebalancePlanStatus.DRAFT,
            portfolio_value=portfolio_value,
            cash_available=cash_available,
            target_cash_weight=result.target_cash_weight,
            reason="Long-only allocation from latest complete signals",
        )
        for allocation in result.allocations:
            instrument = instruments[allocation.asset.instrument_uid]
            entity = TargetAllocation(
                instrument_id=instrument.id,
                target_weight=allocation.target_weight,
                current_weight=allocation.current_weight,
                signal_score=allocation.asset.signal_score,
                target_amount=allocation.target_amount,
                delta_amount=allocation.delta_amount,
                action=allocation.action,
                recommended_lots=allocation.lots,
                reason=allocation.reason,
            )
            entity.instrument = instrument
            plan.allocations.append(entity)
        self._session.add(plan)
        self._session.add(
            AuditLog(
                event_type="rebalance_plan.created",
                message="Rebalance plan created",
                context={
                    "account_id": source_account_id,
                    "allocations_count": len(result.allocations),
                },
            )
        )
        await self._session.commit()
        return plan

    async def list_plans(self, limit: int = 50) -> Sequence[RebalancePlan]:
        result = await self._session.scalars(
            select(RebalancePlan)
            .options(joinedload(RebalancePlan.allocations).joinedload(TargetAllocation.instrument))
            .order_by(RebalancePlan.created_at.desc())
            .limit(limit)
        )
        return result.unique().all()
