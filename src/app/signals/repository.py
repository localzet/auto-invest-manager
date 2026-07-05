from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.entities import AuditLog, Signal, StrategyProfile, WatchlistItem
from app.signals.dto import SignalResult


class SignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_strategy(self) -> StrategyProfile | None:
        return await self._session.scalar(
            select(StrategyProfile).where(StrategyProfile.name == "default").limit(1)
        )

    async def get_watchlist(self) -> Sequence[WatchlistItem]:
        result = await self._session.scalars(
            select(WatchlistItem)
            .options(joinedload(WatchlistItem.instrument))
            .order_by(WatchlistItem.priority.desc())
        )
        return result.all()

    async def save(self, item: WatchlistItem, result: SignalResult, timeframe: str) -> Signal:
        signal = Signal(
            instrument_id=item.instrument_id,
            timeframe=timeframe,
            trend_score=result.trend_score,
            moving_average_score=result.moving_average_score,
            volatility_score=result.volatility_score,
            volume_score=result.volume_score,
            drawdown_score=result.drawdown_score,
            final_score=result.final_score,
            recommendation=result.recommendation,
            price=result.price,
            reason=result.reason,
            model_version=result.model_version,
            calculated_at=result.calculated_at,
        )
        signal.instrument = item.instrument
        self._session.add(signal)
        return signal

    async def latest(self, limit: int) -> Sequence[Signal]:
        result = await self._session.scalars(
            select(Signal)
            .options(joinedload(Signal.instrument))
            .order_by(Signal.calculated_at.desc())
            .limit(limit)
        )
        return result.all()

    def add_audit(self, count: int, model_version: str) -> None:
        self._session.add(
            AuditLog(
                event_type="analysis.completed",
                message="Watchlist signal analysis completed",
                context={"signals_count": count, "model_version": model_version},
            )
        )

    async def commit(self) -> None:
        await self._session.commit()
