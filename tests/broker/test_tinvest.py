from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.broker.errors import BrokerConfigurationError
from app.broker.tinvest import TInvestClient, _decimal


class FakeClientContext:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def __aenter__(self) -> Any:
        return self._client

    async def __aexit__(self, *_: object) -> None:
        return None


def test_decimal_conversion_preserves_nanos() -> None:
    quotation = SimpleNamespace(units=-1, nano=-250_000_000)

    assert _decimal(quotation) == Decimal("-1.25")


async def test_accounts_are_mapped_to_domain_dto() -> None:
    account = SimpleNamespace(
        id="account-id",
        name="Main",
        status=SimpleNamespace(name="OPEN"),
        type=SimpleNamespace(name="BROKER"),
        opened_date=None,
    )

    class Users:
        async def get_accounts(self) -> SimpleNamespace:
            return SimpleNamespace(accounts=[account])

    sdk_client = SimpleNamespace(users=Users())
    provider = TInvestClient(
        token="secret",
        target="test-target",
        client_factory=lambda _token, _target: FakeClientContext(sdk_client),
    )

    result = await provider.get_accounts()

    assert result[0].account_id == "account-id"
    assert result[0].status == "OPEN"


def test_default_client_reports_missing_optional_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.broker.tinvest.find_spec", lambda _: None)

    with pytest.raises(BrokerConfigurationError, match="tinvest extra"):
        TInvestClient(token="secret", target="sandbox")
