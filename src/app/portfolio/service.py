from decimal import ROUND_FLOOR, Decimal

from app.admin.errors import ResourceNotFoundError
from app.broker.interface import BrokerProvider
from app.core.config import Settings
from app.models.entities import Instrument, RebalancePlan
from app.models.enums import AllocationAction
from app.notifications.dto import Notification
from app.notifications.interface import Notifier
from app.notifications.service import NullNotifier
from app.portfolio.dto import AssetInput, OptimizationConstraints
from app.portfolio.optimizer import PortfolioOptimizer
from app.portfolio.planner import RebalancePlanner
from app.portfolio.repository import PortfolioRepository


class RebalanceService:
    def __init__(
        self,
        repository: PortfolioRepository,
        broker: BrokerProvider,
        settings: Settings,
        notifier: Notifier | None = None,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._settings = settings
        self._notifier = notifier or NullNotifier()
        self._optimizer = PortfolioOptimizer()
        self._planner = RebalancePlanner()

    async def create_plan(self) -> RebalancePlan:
        risk = await self._repository.get_risk_profile()
        if risk is None:
            raise ResourceNotFoundError("Active risk profile is not seeded")
        watchlist = await self._repository.get_watchlist()
        if not watchlist:
            raise ResourceNotFoundError("Watchlist is empty")

        account_id = await self._resolve_account_id()
        portfolio = await self._broker.get_portfolio(account_id)
        if portfolio.total_amount.amount <= 0:
            raise ValueError("Broker portfolio value must be positive")

        uids = tuple(item.instrument.instrument_uid for item in watchlist)
        prices = {
            item.instrument_uid: item.price for item in await self._broker.get_last_prices(uids)
        }
        positions = {position.instrument_uid: position for position in portfolio.positions}
        assets: list[AssetInput] = []
        instrument_map: dict[str, Instrument] = {}
        positions_value = Decimal(0)
        for item in watchlist:
            instrument = item.instrument
            signal = await self._repository.get_latest_signal(instrument.id)
            if signal is None:
                raise ResourceNotFoundError(f"No signal found for {instrument.ticker}")
            position = positions.get(instrument.instrument_uid)
            current_value = (
                position.quantity * position.current_price.amount if position else Decimal(0)
            )
            positions_value += current_value
            current_lots = (
                int((position.quantity / instrument.lot).to_integral_value(rounding=ROUND_FLOOR))
                if position
                else 0
            )
            eligible_score = (
                signal.final_score if signal.final_score >= item.min_signal_score else Decimal(0)
            )
            assets.append(
                AssetInput(
                    instrument_uid=instrument.instrument_uid,
                    signal_score=eligible_score,
                    current_value=current_value,
                    current_lots=current_lots,
                    price=prices[instrument.instrument_uid],
                    lot_size=instrument.lot,
                    buy_enabled=item.buy_enabled,
                    sell_enabled=item.sell_enabled,
                    max_weight=item.max_weight,
                    manual_target_weight=item.manual_target_weight,
                    priority=item.priority,
                )
            )
            instrument_map[instrument.instrument_uid] = instrument

        constraints = OptimizationConstraints(
            max_position_weight=risk.max_position_weight,
            min_cash_weight=risk.min_cash_weight,
            rebalance_threshold=risk.rebalance_threshold_percent,
        )
        optimization = self._optimizer.optimize(assets, constraints)
        cash = max(Decimal(0), portfolio.total_amount.amount - positions_value)
        result = self._planner.plan(
            optimization,
            constraints,
            portfolio.total_amount.amount,
            cash,
        )
        plan = await self._repository.save_plan(
            account_id,
            portfolio.total_amount.amount,
            cash,
            result,
            instrument_map,
        )
        actionable_count = sum(
            allocation.action in {AllocationAction.BUY, AllocationAction.SELL}
            for allocation in result.allocations
        )
        await self._notifier.send(
            Notification(
                title="План ребалансировки создан",
                message=(
                    f"Счёт: {account_id}. Стоимость: {portfolio.total_amount.amount}. "
                    f"Действий: {actionable_count}."
                ),
            )
        )
        return plan

    async def list_plans(self) -> list[RebalancePlan]:
        return list(await self._repository.list_plans())

    async def _resolve_account_id(self) -> str:
        if self._settings.tinvest_account_id:
            return self._settings.tinvest_account_id
        accounts = await self._broker.get_accounts()
        if len(accounts) != 1:
            raise ValueError("TINVEST_ACCOUNT_ID is required when account count is not one")
        return accounts[0].account_id
