import asyncio
import random
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.broker.dto import BrokerStreamEvent
from app.broker.interface import BrokerProvider
from app.core.config import Settings
from app.db.session import session_factory
from app.models.enums import (
    BrokerStreamEventKind,
    BrokerStreamStatus,
    BrokerStreamType,
    ReconciliationReason,
)
from app.notifications.dto import Notification, NotificationSeverity
from app.notifications.interface import Notifier
from app.streams.canonical import should_persist_event
from app.streams.lease import RedisStreamLease, StreamLease
from app.streams.processor import schedule_debounced_reconciliation
from app.streams.repository import StreamRepository


class ReconnectPolicy:
    def __init__(self, initial: float, maximum: float, jitter: bool = True) -> None:
        self.initial = initial
        self.maximum = maximum
        self.jitter = jitter

    def delay(self, failures: int) -> float:
        value = min(self.maximum, self.initial * (2 ** max(0, failures - 1)))
        return random.uniform(0, value) if self.jitter else value


class BrokerStreamSupervisor:
    def __init__(
        self,
        broker: BrokerProvider,
        redis: Any,
        settings: Settings,
        notifier: Notifier,
    ) -> None:
        self._broker = broker
        self._redis = redis
        self._settings = settings
        self._notifier = notifier
        self._instance_id = uuid4().hex
        self._lease = RedisStreamLease(redis, settings.broker_stream_lock_ttl_seconds)
        self._reconnect = ReconnectPolicy(
            settings.broker_stream_reconnect_initial_seconds,
            settings.broker_stream_reconnect_max_seconds,
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        await self._redis.set(
            "broker-stream:listener:heartbeat", datetime.now(UTC).isoformat(), ex=90
        )
        if not self._settings.broker_streams_enabled:
            await self._mark_all_disabled()
            await stop_event.wait()
            return
        accounts = await self._broker.get_accounts()
        account_ids = tuple(item.account_id for item in accounts)
        runners: list[asyncio.Task[None]] = []
        definitions = [
            (
                BrokerStreamType.PORTFOLIO,
                self._settings.portfolio_stream_enabled,
                self._broker.capabilities.portfolio_stream_supported,
                self._broker.stream_portfolio,
            ),
            (
                BrokerStreamType.POSITIONS,
                self._settings.positions_stream_enabled,
                self._broker.capabilities.positions_stream_supported,
                self._broker.stream_positions,
            ),
            (
                BrokerStreamType.TRADES,
                self._settings.trades_stream_enabled,
                self._broker.capabilities.trades_stream_supported,
                self._broker.stream_user_trades,
            ),
        ]
        for stream_type, enabled, supported, factory in definitions:
            if not enabled or not supported:
                await self._set_state(stream_type, account_ids, BrokerStreamStatus.DISABLED)
                continue
            runners.append(
                asyncio.create_task(
                    self._run_stream(stream_type, account_ids, factory, stop_event),
                    name=f"broker-{stream_type.value.lower()}-stream",
                )
            )
        if runners:
            await asyncio.gather(*runners, return_exceptions=True)
            if not stop_event.is_set():
                await stop_event.wait()
        else:
            await stop_event.wait()

    async def _run_stream(
        self,
        stream_type: BrokerStreamType,
        account_ids: tuple[str, ...],
        stream_factory: Callable[[tuple[str, ...]], AsyncIterator[BrokerStreamEvent]],
        stop_event: asyncio.Event,
    ) -> None:
        account_hash = _account_set_hash(account_ids)
        lock_key = (
            f"broker-stream:{self._settings.broker_provider}:"
            f"{self._settings.tinvest_target}:{stream_type.value}:{account_hash}"
        )
        lease = await self._lease.acquire(lock_key)
        if lease is None:
            await self._set_state(stream_type, account_ids, BrokerStreamStatus.STOPPED)
            return
        failures = 0
        runner_task = asyncio.current_task()
        renew_task = asyncio.create_task(self._renew_lease(lease, runner_task))
        try:
            while not stop_event.is_set():
                started = datetime.now(UTC)
                await self._set_state(
                    stream_type,
                    account_ids,
                    BrokerStreamStatus.CONNECTING,
                )
                try:
                    iterator = stream_factory(account_ids)
                    await self._set_state(
                        stream_type,
                        account_ids,
                        BrokerStreamStatus.CONNECTING,
                        connected_at=datetime.now(UTC),
                        consecutive_failures=0,
                    )
                    await self._audit(
                        "broker.stream.started",
                        "Broker stream subscription started",
                        {"stream_type": stream_type.value},
                    )
                    while not stop_event.is_set():
                        try:
                            event = await self._next_event(
                                iterator,
                                stop_event,
                            )
                        except StopAsyncIteration:
                            if self._settings.broker_provider == "mock":
                                await stop_event.wait()
                                return
                            raise ConnectionError("Broker stream closed") from None
                        except TimeoutError:
                            await self._set_state(
                                stream_type, account_ids, BrokerStreamStatus.DEGRADED
                            )
                            await self._audit(
                                "broker.stream.stale",
                                "Broker stream heartbeat became stale",
                                {"stream_type": stream_type.value},
                            )
                            raise ConnectionError("Broker stream is stale") from None
                        await self._handle_event(stream_type, account_ids, event)
                    if (datetime.now(UTC) - started).total_seconds() >= (
                        self._settings.broker_stream_reconnect_stable_reset_seconds
                    ):
                        failures = 0
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failures += 1
                    if _terminal_stream_error(error):
                        await self._set_state(
                            stream_type,
                            account_ids,
                            BrokerStreamStatus.FAILED,
                            last_error_code=type(error).__name__,
                            last_error_message="Terminal stream configuration error",
                        )
                        await self._notifier.send(
                            Notification(
                                "Broker stream terminal failure",
                                f"Stream {stream_type.value} stopped ({type(error).__name__}).",
                                NotificationSeverity.CRITICAL,
                            )
                        )
                        await self._audit(
                            "broker.stream.subscription_failed",
                            "Broker stream stopped after terminal error",
                            {"stream_type": stream_type.value},
                        )
                        return
                    delay = self._reconnect.delay(failures)
                    await self._set_state(
                        stream_type,
                        account_ids,
                        BrokerStreamStatus.RECONNECTING,
                        reconnect_count=failures,
                        consecutive_failures=failures,
                        last_error_code=type(error).__name__,
                        last_error_message="Temporary broker stream error",
                        next_reconnect_at=datetime.now(UTC) + timedelta(seconds=delay),
                    )
                    await self._audit(
                        "broker.stream.disconnected",
                        "Broker stream disconnected",
                        {"stream_type": stream_type.value},
                    )
                    await self._audit(
                        "broker.stream.reconnecting",
                        "Broker stream reconnect scheduled",
                        {"stream_type": stream_type.value, "failures": failures},
                    )
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    except TimeoutError:
                        pass
        finally:
            renew_task.cancel()
            await asyncio.gather(renew_task, return_exceptions=True)
            await self._lease.release(lease)
            await self._set_state(stream_type, account_ids, BrokerStreamStatus.STOPPED)
            await self._audit(
                "broker.stream.stopped",
                "Broker stream stopped",
                {"stream_type": stream_type.value},
            )

    async def _handle_event(
        self,
        stream_type: BrokerStreamType,
        account_ids: tuple[str, ...],
        event: BrokerStreamEvent,
    ) -> None:
        now = datetime.now(UTC)
        if event.event_kind == BrokerStreamEventKind.SUBSCRIPTION_STATUS.value:
            await self._set_state(
                stream_type,
                account_ids,
                None,
                last_message_at=now,
                subscription_status=event.payload,
            )
            await self._audit(
                "broker.stream.connected",
                "Broker stream subscription confirmed",
                {"stream_type": stream_type.value},
            )
            if account_ids:
                await schedule_debounced_reconciliation(
                    self._redis,
                    account_ids[0],
                    ReconciliationReason.STREAM_RECONNECTED,
                    self._settings.account_event_debounce_seconds,
                    self._settings.account_event_max_debounce_seconds,
                )
        if event.event_kind == BrokerStreamEventKind.PING.value:
            await self._set_state(
                stream_type,
                account_ids,
                BrokerStreamStatus.CONNECTED,
                last_message_at=now,
                last_ping_at=event.broker_event_time or now,
            )
            return
        if not should_persist_event(event):
            return
        await self._set_state(
            stream_type,
            account_ids,
            BrokerStreamStatus.CONNECTED,
            last_message_at=now,
            last_event_at=now,
        )
        async with session_factory() as session:
            record, created = await StreamRepository(session).persist_event(
                event, f"stream:{uuid4().hex}"
            )
        if created:
            await self._redis.enqueue_job(
                "process_broker_stream_event",
                str(record.id),
                _job_id=f"stream-event:{record.id}",
            )

    async def _renew_lease(self, lease: StreamLease, runner_task: asyncio.Task[Any] | None) -> None:
        while True:
            await asyncio.sleep(self._settings.broker_stream_lock_renew_interval_seconds)
            if not await self._lease.renew(lease):
                if runner_task is not None:
                    runner_task.cancel()
                return

    async def _next_event(
        self,
        iterator: AsyncIterator[BrokerStreamEvent],
        stop_event: asyncio.Event,
    ) -> BrokerStreamEvent:
        event_task = asyncio.create_task(anext(iterator))
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {event_task, stop_task},
            timeout=self._settings.broker_stream_stale_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if not done:
            raise TimeoutError
        if stop_task in done and stop_task.result():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
            raise asyncio.CancelledError
        return event_task.result()

    async def _set_state(
        self,
        stream_type: BrokerStreamType,
        account_ids: tuple[str, ...],
        status: BrokerStreamStatus | None,
        **values: Any,
    ) -> None:
        async with session_factory() as session:
            await StreamRepository(session).upsert_state(
                self._settings.broker_provider,
                self._settings.tinvest_target,
                stream_type,
                _account_set_hash(account_ids),
                self._instance_id,
                status,
                **values,
            )

    async def _mark_all_disabled(self) -> None:
        for stream_type in BrokerStreamType:
            await self._set_state(stream_type, (), BrokerStreamStatus.DISABLED)

    async def _audit(self, event_type: str, message: str, context: dict[str, Any]) -> None:
        async with session_factory() as session:
            await StreamRepository(session).add_audit(
                event_type, "stream-listener", message, context
            )


def _account_set_hash(account_ids: tuple[str, ...]) -> str:
    return sha256(":".join(sorted(account_ids)).encode()).hexdigest()


def _terminal_stream_error(error: Exception) -> bool:
    name = type(error).__name__.upper()
    message = str(error).upper()
    return any(
        marker in name or marker in message
        for marker in (
            "UNAUTHENTICATED",
            "PERMISSION_DENIED",
            "BROKERCONFIGURATION",
            "UNSUPPORTED",
            "INVALID ACCOUNT",
        )
    )
