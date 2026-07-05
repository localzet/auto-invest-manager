from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.broker.dto import InstrumentData
from app.models.entities import (
    AuditLog,
    Instrument,
    RiskProfile,
    StrategyProfile,
    SystemSettings,
    WatchlistItem,
)


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_system_settings(self) -> SystemSettings | None:
        return await self._session.scalar(select(SystemSettings).limit(1))

    async def get_active_risk_profile(self) -> RiskProfile | None:
        return await self._session.scalar(
            select(RiskProfile).where(RiskProfile.is_active.is_(True)).limit(1)
        )

    async def get_default_strategy_profile(self) -> StrategyProfile | None:
        return await self._session.scalar(
            select(StrategyProfile).where(StrategyProfile.name == "default").limit(1)
        )

    async def list_watchlist(self) -> Sequence[WatchlistItem]:
        result = await self._session.scalars(
            select(WatchlistItem)
            .options(joinedload(WatchlistItem.instrument))
            .order_by(WatchlistItem.priority.desc(), WatchlistItem.created_at)
        )
        return result.all()

    async def get_watchlist_item(self, item_id: UUID) -> WatchlistItem | None:
        return await self._session.scalar(
            select(WatchlistItem)
            .where(WatchlistItem.id == item_id)
            .options(joinedload(WatchlistItem.instrument))
        )

    async def get_instrument(self, ticker: str, class_code: str) -> Instrument | None:
        return await self._session.scalar(
            select(Instrument).where(
                Instrument.ticker == ticker.upper(),
                Instrument.class_code == class_code.upper(),
            )
        )

    async def upsert_instrument(self, data: InstrumentData) -> Instrument:
        instrument = await self._session.scalar(
            select(Instrument).where(Instrument.instrument_uid == data.instrument_uid)
        )
        values = {
            "figi": data.figi or None,
            "ticker": data.ticker.upper(),
            "class_code": data.class_code.upper(),
            "name": data.name,
            "instrument_type": data.instrument_type,
            "currency": data.currency.lower(),
            "lot": data.lot,
            "is_active": data.api_trade_available,
        }
        if instrument is None:
            instrument = Instrument(instrument_uid=data.instrument_uid, **values)
            self._session.add(instrument)
        else:
            self.apply_changes(instrument, values)
        await self._session.flush()
        return instrument

    async def add_watchlist_item(
        self, instrument: Instrument, values: Mapping[str, Any]
    ) -> WatchlistItem:
        item = WatchlistItem(instrument_id=instrument.id, **values)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item, attribute_names=["instrument"])
        return item

    async def delete(self, entity: object) -> None:
        await self._session.delete(entity)

    def add_audit(self, event_type: str, message: str, context: dict[str, Any]) -> None:
        self._session.add(AuditLog(event_type=event_type, message=message, context=context))

    @staticmethod
    def apply_changes(entity: object, values: Mapping[str, Any]) -> None:
        for field, value in values.items():
            setattr(entity, field, value)

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
