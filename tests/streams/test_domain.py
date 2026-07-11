from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.broker.dto import (
    BrokerAccountData,
    BrokerOperation,
    BrokerStreamEvent,
    MoneyData,
    OperationsCursorPage,
    PortfolioData,
)
from app.broker.mock import MockBrokerProvider
from app.models.enums import (
    AccountEventType,
    BrokerStreamEventKind,
    ReconciliationReason,
    ReconciliationStatus,
)
from app.streams.canonical import (
    canonical_json,
    event_dedupe_key,
    sanitize_payload,
    should_persist_event,
)
from app.streams.dto import classify_operation
from app.streams.lease import RedisStreamLease
from app.streams.processor import process_event, schedule_debounced_reconciliation
from app.streams.reconciliation import AccountReconciliationService
from app.streams.schemas import mask_account_id
from app.streams.supervisor import ReconnectPolicy, _terminal_stream_error

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


def stream_event(**changes: object) -> BrokerStreamEvent:
    values = {
        "provider": "mock",
        "target": "sandbox",
        "stream_type": "POSITIONS",
        "account_id": "account-1234",
        "broker_event_time": NOW,
        "received_at": NOW,
        "event_kind": "POSITIONS_UPDATED",
        "source_event_id": None,
        "payload": {"cash": "100.00", "currency": "rub"},
    }
    values.update(changes)
    return BrokerStreamEvent(**values)


def test_received_at_is_not_part_of_dedupe_key() -> None:
    first = stream_event(received_at=NOW)
    second = stream_event(received_at=NOW.replace(hour=13))

    assert event_dedupe_key(first) == event_dedupe_key(second)


def test_canonical_payload_sorts_keys() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_payload_sanitization_removes_secrets() -> None:
    value = sanitize_payload(
        {"token": "secret", "nested": {"authorization": "Bearer abc", "safe": 1}}
    )

    assert value == {"nested": {"safe": 1}}


def test_ping_is_not_persistable() -> None:
    assert should_persist_event(stream_event(event_kind="PING")) is False
    assert should_persist_event(stream_event()) is True


@pytest.mark.parametrize(
    ("operation_type", "expected"),
    [
        ("OPERATION_TYPE_INPUT", AccountEventType.DEPOSIT_DETECTED),
        ("OPERATION_TYPE_INPUT_ACQUIRING", AccountEventType.DEPOSIT_DETECTED),
        ("OPERATION_TYPE_INP_MULTI", AccountEventType.DEPOSIT_DETECTED),
        ("OPERATION_TYPE_INPUT_SWIFT", AccountEventType.DEPOSIT_DETECTED),
        ("OPERATION_TYPE_OUTPUT", AccountEventType.WITHDRAWAL_DETECTED),
        ("OPERATION_TYPE_SELL", None),
        ("OPERATION_TYPE_DIVIDEND", None),
        ("OPERATION_TYPE_COUPON", None),
        ("OPERATION_TYPE_INPUT_SECURITIES", None),
        ("OPERATION_TYPE_BUY", None),
        ("OPERATION_TYPE_BROKER_FEE", None),
        ("OPERATION_TYPE_TAX", None),
        ("OPERATION_TYPE_SERVICE_FEE", None),
        ("OPERATION_TYPE_BOND_REPAYMENT", None),
        ("OPERATION_TYPE_DIVIDEND_TAX", None),
        ("OPERATION_TYPE_OUTPUT_SECURITIES", None),
        ("OPERATION_TYPE_ACCRUING_VARMARGIN", None),
        ("OPERATION_TYPE_WRITING_OFF_VARMARGIN", None),
        ("OPERATION_TYPE_CASH_FEE", None),
    ],
)
def test_operation_classification(operation_type: str, expected: AccountEventType | None) -> None:
    assert classify_operation(operation_type, "OPERATION_STATE_EXECUTED").event_type is expected


def test_unfinished_input_is_not_deposit() -> None:
    result = classify_operation("OPERATION_TYPE_INPUT", "OPERATION_STATE_PROGRESS")
    assert result.event_type is None


async def test_mock_stream_is_deterministic() -> None:
    broker = MockBrokerProvider()
    event = stream_event()
    broker.queue_stream_event(event)

    first = [item async for item in broker.stream_positions(("account-1234",))]
    second = [item async for item in broker.stream_positions(("account-1234",))]

    assert first == second == [event]


async def test_mock_operations_cursor_is_paginated() -> None:
    broker = MockBrokerProvider()
    broker.set_operations(
        [operation("one", "OPERATION_TYPE_INPUT"), operation("two", "OPERATION_TYPE_SELL")]
    )
    request = SimpleNamespace(cursor=None, limit=1)

    first = await broker.get_operations_page(request)
    second = await broker.get_operations_page(SimpleNamespace(cursor=first.next_cursor, limit=1))

    assert first.has_next is True
    assert second.items[0].operation_id == "two"


async def test_stream_lease_renews_and_releases_only_owner() -> None:
    redis = LeaseRedis()
    lock = RedisStreamLease(redis, 120)
    lease = await lock.acquire("stream-key")
    assert lease is not None

    assert await lock.renew(lease) is True
    redis.owner = "other"
    assert await lock.renew(lease) is False
    assert await lock.release(lease) is False


def test_reconnect_backoff_is_bounded() -> None:
    policy = ReconnectPolicy(1, 60, jitter=False)
    assert policy.delay(1) == 1
    assert policy.delay(20) == 60


def test_auth_failure_is_terminal() -> None:
    assert _terminal_stream_error(RuntimeError("UNAUTHENTICATED")) is True
    assert _terminal_stream_error(ConnectionError("reset")) is False


async def test_debounce_coalesces_reasons_for_one_account() -> None:
    redis = DebounceRedis()
    await schedule_debounced_reconciliation(
        redis, "account", ReconciliationReason.PORTFOLIO_CHANGED, 20, 60
    )
    await schedule_debounced_reconciliation(
        redis, "account", ReconciliationReason.POSITIONS_CHANGED, 20, 60
    )
    await schedule_debounced_reconciliation(
        redis, "account", ReconciliationReason.USER_TRADE, 20, 60
    )

    assert len(redis.jobs) == 1
    assert next(iter(redis.sets.values())) == {
        "portfolio_changed",
        "positions_changed",
        "user_trade",
    }


async def test_different_accounts_have_independent_debounce() -> None:
    redis = DebounceRedis()
    await schedule_debounced_reconciliation(
        redis, "one", ReconciliationReason.PORTFOLIO_CHANGED, 20, 60
    )
    await schedule_debounced_reconciliation(
        redis, "two", ReconciliationReason.PORTFOLIO_CHANGED, 20, 60
    )

    assert len(redis.jobs) == 2


async def test_subscription_event_is_claimed_and_ignored() -> None:
    event = SimpleNamespace(
        event_kind=BrokerStreamEventKind.SUBSCRIPTION_STATUS,
        account_id="account",
    )
    repository = ProcessorRepository(event)

    result = await process_event(
        repository, DebounceRedis(), SimpleNamespace(send=AsyncMock()), UUID(int=1), 5, 20, 60
    )

    assert result is True
    repository.complete_event.assert_awaited_once_with(event, ignored=True)


async def test_trade_event_records_signal_and_schedules_one_reconciliation() -> None:
    event = SimpleNamespace(
        event_kind=BrokerStreamEventKind.USER_TRADE_EXECUTED,
        account_id="account",
    )
    repository = ProcessorRepository(event)
    redis = DebounceRedis()

    await process_event(
        repository, redis, SimpleNamespace(send=AsyncMock()), UUID(int=1), 5, 20, 60
    )

    repository.record_trade_signal.assert_awaited_once_with(event)
    assert len(redis.jobs) == 1


async def test_poison_event_moves_to_dead_letter_and_notifies() -> None:
    event = SimpleNamespace(
        id=UUID(int=1),
        event_kind=BrokerStreamEventKind.PORTFOLIO_UPDATED,
        account_id="account",
    )
    repository = ProcessorRepository(event)
    repository.complete_event.side_effect = RuntimeError("secret-token")
    repository.fail_event.return_value = True
    notifier = SimpleNamespace(send=AsyncMock())

    result = await process_event(repository, DebounceRedis(), notifier, event.id, 1, 20, 60)

    assert result is False
    assert "secret-token" not in repository.fail_event.await_args.args[3]
    notifier.send.assert_awaited_once()


def test_account_id_is_masked() -> None:
    assert mask_account_id("account-123456") == "***3456"


async def test_confirmed_input_creates_deposit_event() -> None:
    service, repository, broker = reconciliation_service(
        [operation("input", "OPERATION_TYPE_INPUT")]
    )

    result = await service.reconcile(
        "mock-account", {ReconciliationReason.POSITIONS_CHANGED}, "correlation"
    )

    assert result.status is ReconciliationStatus.SUCCEEDED
    assert result.event_types == (AccountEventType.DEPOSIT_DETECTED,)
    broker.get_positions.assert_awaited_once()
    broker.get_portfolio.assert_awaited_once()
    repository.commit_cursor.assert_awaited_once()


async def test_cash_change_without_operation_is_account_change() -> None:
    service, _, _ = reconciliation_service([])

    result = await service.reconcile(
        "mock-account", {ReconciliationReason.POSITIONS_CHANGED}, "cash-change"
    )

    assert result.event_types == (AccountEventType.ACCOUNT_CHANGE,)


async def test_second_operations_page_failure_does_not_advance_cursor() -> None:
    service, repository, broker = reconciliation_service([])
    broker.get_operations_page.side_effect = [
        OperationsCursorPage((operation("one", "OPERATION_TYPE_INPUT"),), "next", True),
        ConnectionError("temporary"),
    ]

    result = await service.reconcile(
        "mock-account", {ReconciliationReason.USER_TRADE}, "page-failure"
    )

    assert result.status is ReconciliationStatus.FAILED
    repository.commit_cursor.assert_not_awaited()


def operation(operation_id: str, operation_type: str) -> BrokerOperation:
    return BrokerOperation(
        operation_id=operation_id,
        cursor=operation_id,
        operation_type=operation_type,
        state="OPERATION_STATE_EXECUTED",
        payment=MoneyData(Decimal("100"), "rub"),
        date=NOW,
        instrument_uid=None,
    )


def reconciliation_service(
    operations: list[BrokerOperation],
) -> tuple[AccountReconciliationService, SimpleNamespace, SimpleNamespace]:
    value = SimpleNamespace(id=UUID(int=1), account_id="mock-account")
    repository = SimpleNamespace(
        create_reconciliation=AsyncMock(return_value=value),
        get_cursor=AsyncMock(return_value=SimpleNamespace(cursor=None, last_operation_time=None)),
        save_account_event=AsyncMock(side_effect=lambda *args: (SimpleNamespace(), True)),
        add_audit=AsyncMock(),
        commit_cursor=AsyncMock(),
        finish_reconciliation=AsyncMock(),
        rollback=AsyncMock(),
    )
    account = BrokerAccountData("mock-account", "Mock", "OPEN", "BROKER", NOW)
    portfolio = PortfolioData(
        "mock-account", MoneyData(Decimal("1000"), "rub"), Decimal(0), (), NOW
    )
    broker = SimpleNamespace(
        get_accounts=AsyncMock(return_value=(account,)),
        get_positions=AsyncMock(return_value=()),
        get_portfolio=AsyncMock(return_value=portfolio),
        get_operations_page=AsyncMock(
            return_value=OperationsCursorPage(tuple(operations), None, False)
        ),
    )
    service = AccountReconciliationService(
        repository,
        SimpleNamespace(save_broker_state=AsyncMock()),
        broker,
        SimpleNamespace(send=AsyncMock()),
        "mock",
        "sandbox",
        24,
        20,
        True,
    )
    return service, repository, broker


class LeaseRedis:
    def __init__(self) -> None:
        self.owner: str | None = None

    async def set(self, key: str, owner: str, **kwargs: object) -> bool:
        if self.owner is not None:
            return False
        self.owner = owner
        return True

    async def eval(self, script: str, count: int, key: str, owner: str, *args: object) -> int:
        if owner != self.owner:
            return 0
        if "expire" in script:
            return 1
        self.owner = None
        return 1


class DebounceRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.jobs: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def set(self, key: str, value: str, **kwargs: object) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value)

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def enqueue_job(self, *args: object, **kwargs: object) -> None:
        self.jobs.append((args, kwargs))


class ProcessorRepository:
    def __init__(self, event: object) -> None:
        self.claim_event = AsyncMock(return_value=event)
        self.complete_event = AsyncMock()
        self.record_trade_signal = AsyncMock()
        self.fail_event = AsyncMock(return_value=False)
