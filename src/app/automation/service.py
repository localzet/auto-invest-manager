import asyncio
from datetime import UTC, datetime
from hashlib import sha256

from app.admin.errors import ResourceNotFoundError
from app.automation.dto import AutomationCycleRequest, AutomationCycleResult
from app.automation.lock import RedisCycleLock
from app.automation.repository import AutomationRepository
from app.automation.retry import RetryPolicy
from app.broker.errors import BrokerRateLimitError
from app.broker.interface import BrokerProvider
from app.execution.service import ExecutionService
from app.models.entities import AutomationRun
from app.models.enums import (
    AllocationAction,
    AutomationRunStatus,
    AutomationStep,
    PlannedOrderStatus,
    TradeMode,
)
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.interface import Notifier
from app.portfolio.service import RebalanceService
from app.signals.service import SignalAnalysisService


class AutomationCycleService:
    def __init__(
        self,
        repository: AutomationRepository,
        broker: BrokerProvider,
        signal_service: SignalAnalysisService,
        rebalance_service: RebalanceService,
        execution_service: ExecutionService,
        cycle_lock: RedisCycleLock,
        retry_policy: RetryPolicy,
        notifier: Notifier,
        timeout_seconds: int,
        preferred_account_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._signal_service = signal_service
        self._rebalance_service = rebalance_service
        self._execution_service = execution_service
        self._cycle_lock = cycle_lock
        self._retry = retry_policy
        self._notifier = notifier
        self._timeout_seconds = timeout_seconds
        self._preferred_account_id = preferred_account_id

    async def run(self, request: AutomationCycleRequest) -> AutomationCycleResult:
        settings = await self._repository.get_settings()
        if settings is None:
            raise ResourceNotFoundError("System settings are not seeded")
        run, created = await self._resolve_run(request, settings.trade_mode)
        if not created or run.status is not AutomationRunStatus.PENDING:
            return AutomationCycleResult(run.id, run.status, "duplicate_correlation_id")

        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._run_guarded(run, request.actor, settings)
        except TimeoutError:
            await self._fail(run, request.actor, "run_timeout", "Automation cycle timed out")
        except BrokerRateLimitError:
            await self._fail(
                run, request.actor, "broker_rate_limited", "Broker read rate limit exceeded"
            )
        except Exception as error:
            await self._fail(
                run,
                request.actor,
                "cycle_failed",
                f"Automation cycle failed ({type(error).__name__})",
            )
        return AutomationCycleResult(run.id, AutomationRunStatus.FAILED, run.error_code)

    async def _resolve_run(
        self, request: AutomationCycleRequest, trade_mode: TradeMode
    ) -> tuple[AutomationRun, bool]:
        if request.run_id is not None:
            run = await self._repository.get(request.run_id)
            if run is None:
                raise ResourceNotFoundError("Automation run not found")
            return run, run.status is AutomationRunStatus.PENDING
        return await self._repository.create(
            request.trigger,
            request.correlation_id,
            trade_mode,
            request.actor,
        )

    async def _run_guarded(
        self, run: AutomationRun, actor: str, settings: object
    ) -> AutomationCycleResult:
        await self._repository.update_step(run, AutomationStep.SAFETY_CHECK)
        trade_mode = settings.trade_mode
        run.trade_mode = trade_mode
        if trade_mode is TradeMode.OFF:
            return await self._skip(run, actor, "trade_mode_off")
        if settings.kill_switch:
            await self._repository.add_audit(
                "automation.safety.rejected",
                actor,
                "Automation stopped by kill switch",
                {"run_id": str(run.id)},
            )
            return await self._skip(run, actor, "kill_switch_enabled")

        await self._repository.update_step(run, AutomationStep.ACCOUNT_SYNC)
        accounts = await self._retry.run(self._broker.get_accounts)
        account = self._select_account(accounts)
        account_id = account.account_id
        lease = await self._cycle_lock.acquire(account_id)
        if lease is None:
            await self._repository.add_audit(
                "automation.lock.rejected",
                actor,
                "Parallel automation cycle rejected",
                {"run_id": str(run.id)},
            )
            return await self._skip(run, actor, "cycle_already_running")

        try:
            await self._repository.mark_running(run, account_id)
            return await self._run_pipeline(run, actor, trade_mode, account)
        finally:
            await self._cycle_lock.release(lease)

    async def _run_pipeline(
        self, run: AutomationRun, actor: str, trade_mode: TradeMode, account: object
    ) -> AutomationCycleResult:
        account_id = account.account_id
        await self._repository.update_step(run, AutomationStep.PORTFOLIO_SYNC)
        portfolio = await self._retry.run(lambda: self._broker.get_portfolio(account_id))
        await self._repository.save_broker_state(
            account, portfolio, trade_mode is TradeMode.SANDBOX
        )
        await self._repository.update_step(run, AutomationStep.MARKET_DATA_SYNC)
        await self._repository.update_step(run, AutomationStep.SIGNAL_ANALYSIS)
        signals = await self._signal_service.run()
        await self._repository.update_step(run, AutomationStep.PORTFOLIO_OPTIMIZATION)
        run.signals_count = len(signals)

        if trade_mode is TradeMode.SIGNAL_ONLY:
            return await self._succeed(run, actor)

        await self._repository.update_step(run, AutomationStep.REBALANCE_PLANNING)
        plan = await self._rebalance_service.create_plan()
        run.rebalance_plan_id = plan.id
        market_open = await self._market_is_open(plan, actor)
        if not market_open:
            return await self._succeed(run, actor, {"execution_skipped": "market_closed"})

        await self._repository.update_step(run, AutomationStep.EXECUTION_PLANNING)
        orders = await self._execution_service.plan_orders(plan.id)
        run.planned_orders_count = len(orders)
        if orders:
            await self._repository.add_audit(
                "automation.orders.planned",
                actor,
                "Automation planned orders",
                {"run_id": str(run.id), "orders_count": len(orders)},
            )
            await self._notifier.send(
                Notification(
                    "Automation создала заявки",
                    f"Создано planned orders: {len(orders)}. Режим: {trade_mode.value}.",
                    NotificationSeverity.WARNING,
                )
            )

        await self._repository.update_step(run, AutomationStep.MODE_EXECUTION)
        if trade_mode is TradeMode.DRY_RUN:
            for order in orders:
                await self._execution_service.execute(order.id)
            run.virtual_trades_count = len(orders)
        elif trade_mode is TradeMode.SANDBOX:
            for order in orders:
                await self._execution_service.execute_sandbox(order.id)
            run.executed_orders_count = len(orders)
        elif trade_mode is TradeMode.REAL_MANUAL_CONFIRM:
            if any(order.status is not PlannedOrderStatus.WAITING_CONFIRMATION for order in orders):
                raise RuntimeError("Manual-confirmation order has unsafe status")
        else:
            return await self._skip(run, actor, "unsupported_trade_mode")

        if trade_mode in {TradeMode.DRY_RUN, TradeMode.SANDBOX} and orders:
            await self._repository.add_audit(
                "automation.execution.completed",
                actor,
                "Automation execution completed",
                {"run_id": str(run.id), "mode": trade_mode.value, "count": len(orders)},
            )
            await self._notifier.send(
                Notification(
                    "Automation execution завершён",
                    f"Режим: {trade_mode.value}. Обработано заявок: {len(orders)}.",
                )
            )
        await self._repository.update_step(run, AutomationStep.FINAL_RECONCILIATION)
        return await self._succeed(run, actor)

    async def _market_is_open(self, plan: object, actor: str) -> bool:
        actionable = [
            allocation
            for allocation in plan.allocations
            if allocation.action in {AllocationAction.BUY, AllocationAction.SELL}
            and allocation.recommended_lots > 0
        ]
        for allocation in actionable:
            status = await self._retry.run(
                lambda uid=allocation.instrument.instrument_uid: self._broker.get_trading_status(
                    uid
                )
            )
            if not status.api_trade_available or not status.limit_order_available:
                await self._repository.add_audit(
                    "automation.safety.rejected",
                    actor,
                    "Execution skipped because market is closed",
                    {"reason": "market_closed"},
                )
                return False
        return True

    async def _succeed(
        self, run: AutomationRun, actor: str, metadata: dict[str, str] | None = None
    ) -> AutomationCycleResult:
        await self._repository.update_step(run, AutomationStep.COMPLETED)
        await self._repository.finish(run, AutomationRunStatus.SUCCEEDED, actor, metadata=metadata)
        return AutomationCycleResult(run.id, AutomationRunStatus.SUCCEEDED)

    async def _skip(self, run: AutomationRun, actor: str, reason: str) -> AutomationCycleResult:
        await self._repository.finish(
            run,
            AutomationRunStatus.SKIPPED,
            actor,
            reason=reason,
            metadata={"reason": reason},
        )
        if reason in {"trade_mode_off", "kill_switch_enabled"}:
            await self._notifier.send(
                Notification(
                    "Automation остановлена safety check",
                    f"Причина: {reason}.",
                    NotificationSeverity.WARNING,
                )
            )
        return AutomationCycleResult(run.id, AutomationRunStatus.SKIPPED, reason)

    async def _fail(self, run: AutomationRun, actor: str, code: str, safe_message: str) -> None:
        await self._repository.finish(
            run,
            AutomationRunStatus.FAILED,
            actor,
            reason=safe_message,
            error_code=code,
            error_message=safe_message,
        )
        await self._notifier.send(
            Notification(
                "Automation cycle failed",
                f"Run {run.id}: {code}.",
                NotificationSeverity.CRITICAL,
            )
        )

    def _select_account(self, accounts: tuple[object, ...]) -> object:
        if self._preferred_account_id:
            for item in accounts:
                if item.account_id == self._preferred_account_id:
                    return item
            raise ValueError("Configured broker account was not returned by provider")
        if len(accounts) != 1:
            raise ValueError("Exactly one broker account is required for automation")
        return accounts[0]


def scheduled_correlation_id(
    account_id: str, strategy_id: object, interval_seconds: int, now: datetime | None = None
) -> str:
    timestamp = int((now or datetime.now(UTC)).timestamp())
    bucket = timestamp // interval_seconds
    source = f"{account_id}:{strategy_id}:{bucket}".encode()
    return f"scheduled:{sha256(source).hexdigest()}"
