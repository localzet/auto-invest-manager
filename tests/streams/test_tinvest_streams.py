from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.broker.tinvest import TInvestClient

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)


class ClientContext:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def __aenter__(self) -> Any:
        return self.client

    async def __aexit__(self, *_: object) -> None:
        return None


class OperationsStream:
    async def portfolio_stream(self, *, accounts: list[str]) -> Any:
        yield SimpleNamespace(
            ping=None,
            subscriptions=None,
            portfolio=SimpleNamespace(
                account_id=accounts[0],
                total_amount_portfolio=money(1000),
                positions=[],
            ),
        )

    async def positions_stream(self, *, accounts: list[str]) -> Any:
        yield SimpleNamespace(
            ping=None,
            subscriptions=None,
            position=SimpleNamespace(
                account_id=accounts[0],
                date=NOW,
                money=[SimpleNamespace(available_value=money(500))],
                securities=[],
            ),
        )


class OrdersStream:
    async def trades_stream(self, *, accounts: list[str]) -> Any:
        yield SimpleNamespace(
            ping=None,
            order_trades=SimpleNamespace(
                account_id=accounts[0],
                order_id="order",
                instrument_uid="uid",
                figi="figi",
                direction=SimpleNamespace(name="ORDER_DIRECTION_BUY"),
                created_at=NOW,
                trades=[
                    SimpleNamespace(
                        trade_id="trade",
                        quantity=2,
                        price=quotation(123),
                        date_time=NOW,
                    )
                ],
            ),
        )


def provider() -> TInvestClient:
    client = SimpleNamespace(operations_stream=OperationsStream(), orders_stream=OrdersStream())
    return TInvestClient(
        "secret",
        "sandbox-invest-public-api.tinkoff.ru:443",
        client_factory=lambda *_: ClientContext(client),
    )


async def test_portfolio_stream_is_normalized_to_domain_dto() -> None:
    event = [item async for item in provider().stream_portfolio(("account",))][0]

    assert event.event_kind == "PORTFOLIO_UPDATED"
    assert event.payload == {
        "total_amount": "1000",
        "currency": "rub",
        "positions_count": 0,
    }
    assert isinstance(event.payload, dict)


async def test_positions_stream_is_normalized_to_domain_dto() -> None:
    event = [item async for item in provider().stream_positions(("account",))][0]

    assert event.event_kind == "POSITIONS_UPDATED"
    assert event.broker_event_time == NOW
    assert event.payload["money"][0]["amount"] == "500"


async def test_trade_stream_preserves_trade_identity_and_decimal_price() -> None:
    event = [item async for item in provider().stream_user_trades(("account",))][0]

    assert event.source_event_id == "trade"
    assert event.payload["trades"][0] == {
        "trade_id": "trade",
        "quantity": 2,
        "price": "123",
        "created_at": NOW.isoformat(),
    }


async def test_sandbox_configuration_keeps_sandbox_target_in_events() -> None:
    event = [item async for item in provider().stream_portfolio(("account",))][0]

    assert event.target == "sandbox-invest-public-api.tinkoff.ru:443"


def money(units: int) -> SimpleNamespace:
    return SimpleNamespace(units=units, nano=0, currency="rub")


def quotation(units: int) -> SimpleNamespace:
    return SimpleNamespace(units=units, nano=0)
