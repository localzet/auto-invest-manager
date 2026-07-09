from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.admin.errors import ResourceConflictError, ResourceNotFoundError
from app.broker.dto import SandboxOrderRequest
from app.broker.interface import BrokerProvider
from app.core.config import Settings
from app.execution.dto import ExecutionAllocation, PlannedOrderData, RiskContext
from app.execution.errors import RiskRejectedError
from app.execution.planner import ExecutionPlanner
from app.execution.repository import ExecutionRepository
from app.execution.risk import RiskManager
from app.models.entities import ExecutionOrder, PlannedOrder, VirtualTrade
from app.models.enums import (
    AllocationAction,
    OrderDirection,
    OrderType,
    PlannedOrderStatus,
    TradeMode,
)


class ExecutionService:
    def __init__(
        self,
        repository: ExecutionRepository,
        broker: BrokerProvider,
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._settings = settings
        self._clock = clock
        self._planner = ExecutionPlanner()
        self._risk_manager = RiskManager()

    async def plan_orders(self, plan_id: UUID) -> list[PlannedOrder]:
        plan = await self._repository.get_plan(plan_id)
        if plan is None:
            raise ResourceNotFoundError("Rebalance plan not found")
        system = await self._repository.get_settings()
        risk = await self._repository.get_risk_profile()
        if system is None or risk is None:
            raise ResourceNotFoundError("System settings or risk profile are not seeded")
        allowed_modes = {
            TradeMode.DRY_RUN,
            TradeMode.SANDBOX,
            TradeMode.REAL_MANUAL_CONFIRM,
        }
        if system.trade_mode not in allowed_modes:
            raise ResourceConflictError(
                "System trade mode must allow dry-run, sandbox or manual confirmation"
            )
        if system.trade_mode is TradeMode.SANDBOX:
            self._ensure_sandbox_configuration()

        actionable = [
            allocation
            for allocation in plan.allocations
            if allocation.action in {AllocationAction.BUY, AllocationAction.SELL}
            and allocation.recommended_lots > 0
        ]
        prices = {
            item.instrument_uid: item.price
            for item in await self._broker.get_last_prices(
                tuple(allocation.instrument.instrument_uid for allocation in actionable)
            )
        }
        inputs = [
            ExecutionAllocation(
                instrument_uid=allocation.instrument.instrument_uid,
                ticker=allocation.instrument.ticker,
                direction=(
                    OrderDirection.BUY
                    if allocation.action is AllocationAction.BUY
                    else OrderDirection.SELL
                ),
                lots=allocation.recommended_lots,
                lot_size=allocation.instrument.lot,
                market_price=prices[allocation.instrument.instrument_uid],
                reason=allocation.reason,
            )
            for allocation in actionable
        ]
        data = self._planner.plan(
            plan.id,
            inputs,
            risk.default_order_type,
            risk.max_slippage_percent,
            system.trade_mode,
        )
        return await self._repository.save_orders(plan, data)

    async def execute(self, order_id: UUID) -> VirtualTrade:
        order = await self._repository.get_order(order_id)
        if order is None:
            raise ResourceNotFoundError("Planned order not found")
        if order.virtual_trade is not None:
            return order.virtual_trade
        if order.status is not PlannedOrderStatus.PLANNED:
            raise ResourceConflictError(f"Order cannot be executed from status {order.status}")

        context = await self._build_risk_context(order, TradeMode.DRY_RUN)
        decision = self._risk_manager.evaluate(self._to_data(order), context)
        if not decision.allowed:
            await self._repository.reject(order, decision.reasons)
            raise RiskRejectedError(decision.reasons)
        return await self._repository.simulate(order)

    async def execute_sandbox(self, order_id: UUID) -> ExecutionOrder:
        self._ensure_sandbox_configuration()
        order = await self._repository.get_order(order_id)
        if order is None:
            raise ResourceNotFoundError("Planned order not found")
        existing = await self._repository.get_execution_order(order.id)
        if existing is not None:
            return existing
        if order.status is not PlannedOrderStatus.PLANNED:
            raise ResourceConflictError(f"Order cannot be executed from status {order.status}")

        context = await self._build_risk_context(order, TradeMode.SANDBOX)
        decision = self._risk_manager.evaluate(self._to_data(order), context)
        if not decision.allowed:
            await self._repository.reject(order, decision.reasons)
            raise RiskRejectedError(decision.reasons)
        result = await self._broker.post_sandbox_order(
            SandboxOrderRequest(
                account_id=order.account_id,
                instrument_uid=order.instrument.instrument_uid,
                quantity_lots=order.lots,
                direction=order.direction,
                order_type=order.order_type,
                price=order.limit_price,
                order_id=order.idempotency_key,
            )
        )
        return await self._repository.save_sandbox_execution(order, result)

    async def _build_risk_context(
        self, order: PlannedOrder, required_mode: TradeMode
    ) -> RiskContext:
        system = await self._repository.get_settings()
        risk = await self._repository.get_risk_profile()
        watchlist = await self._repository.get_watchlist_item(order.instrument_id)
        if system is None or risk is None:
            raise ResourceNotFoundError("System settings or risk profile are not seeded")
        portfolio = await self._broker.get_portfolio(order.account_id)
        price = (await self._broker.get_last_prices((order.instrument.instrument_uid,)))[0]
        trading = await self._broker.get_trading_status(order.instrument.instrument_uid)
        position = next(
            (
                item
                for item in portfolio.positions
                if item.instrument_uid == order.instrument.instrument_uid
            ),
            None,
        )
        positions_value = sum(
            (item.quantity * item.current_price.amount for item in portfolio.positions),
            Decimal(0),
        )
        latest_trade_time = await self._repository.latest_trade_time(order.instrument_id)
        now = self._clock()
        return RiskContext(
            kill_switch=system.kill_switch,
            trade_mode=system.trade_mode,
            required_trade_mode=required_mode,
            account_id=order.account_id,
            expected_account_id=portfolio.account_id,
            in_watchlist=watchlist is not None,
            direction_allowed=(
                watchlist is not None
                and (
                    watchlist.buy_enabled
                    if order.direction is OrderDirection.BUY
                    else watchlist.sell_enabled
                )
            ),
            api_trade_available=trading.api_trade_available,
            order_type_available=(
                trading.limit_order_available
                if order.order_type is OrderType.LIMIT
                else trading.market_order_available
            ),
            price_time=price.time,
            now=now,
            max_price_age_seconds=self._settings.market_price_max_age_seconds,
            market_price=price.price,
            max_slippage_percent=risk.max_slippage_percent,
            cash_available=max(Decimal(0), portfolio.total_amount.amount - positions_value),
            current_position_lots=(
                int(position.quantity / order.instrument.lot) if position else 0
            ),
            current_position_value=(
                position.quantity * position.current_price.amount if position else Decimal(0)
            ),
            portfolio_value=portfolio.total_amount.amount,
            max_position_weight=risk.max_position_weight,
            max_trade_amount=risk.max_trade_amount,
            daily_trades=await self._repository.count_trades_since(
                now.replace(hour=0, minute=0, second=0, microsecond=0)
            ),
            max_daily_trades=risk.max_daily_trades,
            cooldown_active=(
                latest_trade_time is not None
                and now - latest_trade_time < timedelta(seconds=risk.trade_cooldown_seconds)
            ),
            duplicate_active_order=await self._repository.has_duplicate_order(order),
            idempotency_key_exists=False,
        )

    def _ensure_sandbox_configuration(self) -> None:
        if (
            self._settings.broker_provider != "tinvest"
            or self._settings.tinvest_target != "sandbox"
        ):
            raise ResourceConflictError(
                "Sandbox execution requires BROKER_PROVIDER=tinvest and TINVEST_TARGET=sandbox"
            )

    async def list_virtual_trades(self) -> list[VirtualTrade]:
        return await self._repository.list_virtual_trades()

    async def list_orders(self) -> list[PlannedOrder]:
        return await self._repository.list_orders()

    async def approve(self, order_id: UUID) -> PlannedOrder:
        order = await self._get_manual_order(order_id)
        if order.status is not PlannedOrderStatus.WAITING_CONFIRMATION:
            raise ResourceConflictError(
                f"Order cannot be approved from status {order.status.value}"
            )
        return await self._repository.set_confirmation_status(order, PlannedOrderStatus.APPROVED)

    async def reject(self, order_id: UUID) -> PlannedOrder:
        order = await self._get_manual_order(order_id)
        if order.status not in {
            PlannedOrderStatus.WAITING_CONFIRMATION,
            PlannedOrderStatus.APPROVED,
        }:
            raise ResourceConflictError(
                f"Order cannot be rejected from status {order.status.value}"
            )
        return await self._repository.set_confirmation_status(order, PlannedOrderStatus.REJECTED)

    async def _get_manual_order(self, order_id: UUID) -> PlannedOrder:
        order = await self._repository.get_order(order_id)
        if order is None:
            raise ResourceNotFoundError("Planned order not found")
        if order.trade_mode is not TradeMode.REAL_MANUAL_CONFIRM:
            raise ResourceConflictError("Order is not a real manual-confirmation order")
        system = await self._repository.get_settings()
        if system is None or system.trade_mode is not TradeMode.REAL_MANUAL_CONFIRM:
            raise ResourceConflictError("System trade mode is not REAL_MANUAL_CONFIRM")
        return order

    @staticmethod
    def _to_data(order: PlannedOrder) -> PlannedOrderData:
        return PlannedOrderData(
            instrument_uid=order.instrument.instrument_uid,
            ticker=order.instrument.ticker,
            direction=order.direction,
            lots=order.lots,
            lot_size=order.instrument.lot,
            order_type=order.order_type,
            limit_price=order.limit_price,
            reason=order.reason,
            trade_mode=order.trade_mode,
            idempotency_key=order.idempotency_key,
        )
