from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.admin.errors import ResourceConflictError, ResourceNotFoundError
from app.admin.repository import AdminRepository
from app.admin.schemas import (
    InstrumentReference,
    RiskProfileUpdate,
    StrategyProfileUpdate,
    SystemSettingsUpdate,
    WatchlistItemCreate,
    WatchlistItemUpdate,
)
from app.broker.dto import BrokerAccountData
from app.broker.interface import BrokerProvider
from app.core.config import Settings
from app.models.entities import (
    AuditLog,
    Instrument,
    RiskProfile,
    StrategyProfile,
    SystemSettings,
    WatchlistItem,
)


class AdminService:
    def __init__(
        self,
        repository: AdminRepository,
        broker: BrokerProvider,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._settings = settings

    @property
    def real_trading_enabled_by_env(self) -> bool:
        return self._settings.enable_real_trading

    async def get_accounts(self) -> tuple[BrokerAccountData, ...]:
        return await self._broker.get_accounts()

    async def list_audit_logs(self) -> list[AuditLog]:
        return list(await self._repository.list_audit_logs())

    async def get_system_settings(self) -> SystemSettings:
        value = await self._repository.get_system_settings()
        if value is None:
            raise ResourceNotFoundError("System settings are not seeded")
        return value

    async def update_system_settings(self, payload: SystemSettingsUpdate) -> SystemSettings:
        entity = await self.get_system_settings()
        changes = payload.model_dump(exclude_unset=True)
        self._repository.apply_changes(entity, changes)
        self._repository.add_audit(
            "system_settings.updated",
            "System settings updated",
            {key: str(value) for key, value in changes.items()},
        )
        await self._repository.flush()
        await self._repository.commit()
        return entity

    async def sync_instruments(self, references: list[InstrumentReference]) -> list[Instrument]:
        synced: list[Instrument] = []
        seen: set[tuple[str, str]] = set()
        for reference in references:
            key = (reference.ticker.upper(), reference.class_code.upper())
            if key in seen:
                continue
            seen.add(key)
            data = await self._broker.find_instrument(*key)
            synced.append(await self._repository.upsert_instrument(data))
        self._repository.add_audit(
            "instruments.synced",
            "Broker instruments synchronized",
            {"count": len(synced)},
        )
        await self._repository.commit()
        return synced

    async def list_watchlist(self) -> list[WatchlistItem]:
        return list(await self._repository.list_watchlist())

    async def add_watchlist_item(self, payload: WatchlistItemCreate) -> WatchlistItem:
        data = await self._broker.find_instrument(payload.ticker, payload.class_code)
        instrument = await self._repository.upsert_instrument(data)
        existing = await self._repository.get_instrument(payload.ticker, payload.class_code)
        if existing is not None:
            items = await self._repository.list_watchlist()
            if any(item.instrument_id == existing.id for item in items):
                raise ResourceConflictError("Instrument is already in the watchlist")
        values = payload.model_dump(exclude={"ticker", "class_code"})
        item = await self._repository.add_watchlist_item(instrument, values)
        self._repository.add_audit(
            "watchlist.added",
            "Instrument added to watchlist",
            {"ticker": data.ticker, "class_code": data.class_code},
        )
        try:
            await self._repository.commit()
        except IntegrityError as error:
            raise ResourceConflictError("Instrument is already in the watchlist") from error
        return item

    async def update_watchlist_item(
        self, item_id: UUID, payload: WatchlistItemUpdate
    ) -> WatchlistItem:
        item = await self._get_watchlist_item(item_id)
        changes = payload.model_dump(exclude_unset=True)
        effective_max = changes.get("max_weight", item.max_weight)
        effective_target = changes.get("manual_target_weight", item.manual_target_weight)
        if (
            effective_max is not None
            and effective_target is not None
            and effective_target > effective_max
        ):
            raise ResourceConflictError("manual_target_weight cannot exceed max_weight")
        self._repository.apply_changes(item, changes)
        self._repository.add_audit(
            "watchlist.updated", "Watchlist item updated", {"item_id": str(item_id)}
        )
        await self._repository.flush()
        await self._repository.commit()
        return item

    async def remove_watchlist_item(self, item_id: UUID) -> None:
        item = await self._get_watchlist_item(item_id)
        await self._repository.delete(item)
        self._repository.add_audit(
            "watchlist.removed", "Instrument removed from watchlist", {"item_id": str(item_id)}
        )
        await self._repository.commit()

    async def _get_watchlist_item(self, item_id: UUID) -> WatchlistItem:
        item = await self._repository.get_watchlist_item(item_id)
        if item is None:
            raise ResourceNotFoundError("Watchlist item not found")
        return item

    async def get_risk_profile(self) -> RiskProfile:
        entity = await self._repository.get_active_risk_profile()
        if entity is None:
            raise ResourceNotFoundError("Active risk profile is not seeded")
        return entity

    async def update_risk_profile(self, payload: RiskProfileUpdate) -> RiskProfile:
        entity = await self.get_risk_profile()
        changes = payload.model_dump(exclude_unset=True)
        max_position = changes.get("max_position_weight", entity.max_position_weight)
        min_cash = changes.get("min_cash_weight", entity.min_cash_weight)
        if max_position + min_cash > 1:
            raise ResourceConflictError("max_position_weight + min_cash_weight cannot exceed 1")
        self._repository.apply_changes(entity, changes)
        self._repository.add_audit(
            "risk_profile.updated", "Risk profile updated", {"profile_id": str(entity.id)}
        )
        await self._repository.flush()
        await self._repository.commit()
        return entity

    async def get_strategy_profile(self) -> StrategyProfile:
        entity = await self._repository.get_default_strategy_profile()
        if entity is None:
            raise ResourceNotFoundError("Default strategy profile is not seeded")
        return entity

    async def update_strategy_profile(self, payload: StrategyProfileUpdate) -> StrategyProfile:
        entity = await self.get_strategy_profile()
        changes = payload.model_dump(exclude_unset=True)
        self._repository.apply_changes(entity, changes)
        self._repository.add_audit(
            "strategy_profile.updated",
            "Strategy profile updated",
            {"profile_id": str(entity.id)},
        )
        await self._repository.flush()
        await self._repository.commit()
        return entity
