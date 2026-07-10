from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.dto import BrokerAccountData, PortfolioData
from app.models.entities import (
    AuditLog,
    AutomationRun,
    BrokerAccount,
    CashSnapshot,
    Instrument,
    PortfolioSnapshot,
    Position,
    StrategyProfile,
    SystemSettings,
)
from app.models.enums import (
    AutomationRunStatus,
    AutomationStep,
    AutomationTrigger,
    TradeMode,
)


class AutomationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_settings(self) -> SystemSettings | None:
        return await self._session.scalar(select(SystemSettings).limit(1))

    async def get_strategy(self) -> StrategyProfile | None:
        return await self._session.scalar(
            select(StrategyProfile).where(StrategyProfile.name == "default").limit(1)
        )

    async def get(self, run_id: UUID) -> AutomationRun | None:
        return await self._session.get(AutomationRun, run_id)

    async def get_by_correlation(self, correlation_id: str) -> AutomationRun | None:
        return await self._session.scalar(
            select(AutomationRun).where(AutomationRun.correlation_id == correlation_id)
        )

    async def create(
        self,
        trigger: AutomationTrigger,
        correlation_id: str,
        trade_mode: TradeMode,
        actor: str,
    ) -> tuple[AutomationRun, bool]:
        existing = await self.get_by_correlation(correlation_id)
        if existing is not None:
            return existing, False
        run = AutomationRun(
            trigger=trigger,
            status=AutomationRunStatus.PENDING,
            trade_mode=trade_mode,
            correlation_id=correlation_id,
            current_step=AutomationStep.SAFETY_CHECK,
            run_metadata={},
        )
        self._session.add(run)
        self._session.add(
            AuditLog(
                event_type="automation.run.started",
                actor=actor,
                message="Automation run queued",
                context={"correlation_id": correlation_id, "trigger": trigger.value},
            )
        )
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_correlation(correlation_id)
            if existing is None:
                raise
            return existing, False
        return run, True

    async def mark_running(self, run: AutomationRun, account_id: str) -> None:
        now = datetime.now(UTC)
        run.status = AutomationRunStatus.RUNNING
        run.account_id = account_id
        run.started_at = now
        run.heartbeat_at = now
        await self._session.commit()

    async def save_broker_state(
        self,
        account_data: BrokerAccountData,
        portfolio_data: PortfolioData,
        is_sandbox: bool,
    ) -> None:
        account = await self._session.scalar(
            select(BrokerAccount).where(BrokerAccount.broker_account_id == account_data.account_id)
        )
        if account is None:
            account = BrokerAccount(
                broker_account_id=account_data.account_id,
                name=account_data.name,
                is_sandbox=is_sandbox,
                is_active=True,
            )
            self._session.add(account)
            await self._session.flush()
        else:
            account.name = account_data.name
            account.is_sandbox = is_sandbox
            account.is_active = True
        snapshot = PortfolioSnapshot(
            account_id=account.id,
            total_amount=portfolio_data.total_amount.amount,
            expected_yield=portfolio_data.expected_yield,
            captured_at=portfolio_data.captured_at,
        )
        self._session.add(snapshot)
        await self._session.flush()
        instrument_uids = [item.instrument_uid for item in portfolio_data.positions]
        instruments = {
            instrument.instrument_uid: instrument
            for instrument in (
                await self._session.scalars(
                    select(Instrument).where(Instrument.instrument_uid.in_(instrument_uids))
                )
            ).all()
        }
        positions_value = 0
        for item in portfolio_data.positions:
            instrument = instruments.get(item.instrument_uid)
            if instrument is None:
                continue
            current_value = item.quantity * item.current_price.amount
            positions_value += current_value
            self._session.add(
                Position(
                    portfolio_snapshot_id=snapshot.id,
                    instrument_id=instrument.id,
                    quantity=item.quantity,
                    current_price=item.current_price.amount,
                    current_value=current_value,
                    average_price=(item.average_price.amount if item.average_price else None),
                )
            )
        self._session.add(
            CashSnapshot(
                portfolio_snapshot_id=snapshot.id,
                currency=portfolio_data.total_amount.currency,
                amount=max(0, portfolio_data.total_amount.amount - positions_value),
            )
        )
        await self._session.commit()

    async def update_step(self, run: AutomationRun, step: AutomationStep, **values: Any) -> None:
        run.current_step = step
        run.heartbeat_at = datetime.now(UTC)
        for field, value in values.items():
            setattr(run, field, value)
        await self._session.commit()

    async def finish(
        self,
        run: AutomationRun,
        status: AutomationRunStatus,
        actor: str,
        *,
        reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        run.status = status
        run.finished_at = now
        run.heartbeat_at = now
        run.error_code = error_code
        run.error_message = error_message
        run.run_metadata = {**run.run_metadata, **(metadata or {})}
        event = {
            AutomationRunStatus.SUCCEEDED: "automation.run.succeeded",
            AutomationRunStatus.SKIPPED: "automation.run.skipped",
            AutomationRunStatus.FAILED: "automation.run.failed",
        }.get(status, "automation.run.finished")
        self._session.add(
            AuditLog(
                event_type=event,
                severity="warning" if status is not AutomationRunStatus.SUCCEEDED else "info",
                actor=actor,
                message=reason or f"Automation run {status.value.lower()}",
                context={"run_id": str(run.id), "error_code": error_code},
            )
        )
        await self._session.commit()

    async def add_audit(
        self, event_type: str, actor: str, message: str, context: dict[str, Any]
    ) -> None:
        self._session.add(
            AuditLog(
                event_type=event_type,
                actor=actor,
                message=message,
                context=context,
            )
        )
        await self._session.commit()

    async def list_runs(self, limit: int = 100) -> list[AutomationRun]:
        result = await self._session.scalars(
            select(AutomationRun).order_by(AutomationRun.created_at.desc()).limit(limit)
        )
        return list(result.all())

    async def recover_stale(self, threshold: datetime) -> list[AutomationRun]:
        result = await self._session.scalars(
            select(AutomationRun).where(
                AutomationRun.status == AutomationRunStatus.RUNNING,
                AutomationRun.heartbeat_at < threshold,
            )
        )
        runs = list(result.all())
        for run in runs:
            await self.finish(
                run,
                AutomationRunStatus.FAILED,
                "system",
                reason="Stale worker run recovered",
                error_code="stale_worker_run",
                error_message="Worker heartbeat expired",
            )
            await self.add_audit(
                "automation.stale_run.recovered",
                "system",
                "Stale automation run marked failed",
                {"run_id": str(run.id)},
            )
        return runs

    async def running_count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count(AutomationRun.id)).where(
                    AutomationRun.status == AutomationRunStatus.RUNNING
                )
            )
            or 0
        )
