import pytest

from app.broker.errors import BrokerConfigurationError
from app.broker.factory import create_broker_provider
from app.broker.mock import MockBrokerProvider
from app.core.config import Settings


def test_factory_uses_mock_by_default() -> None:
    provider = create_broker_provider(Settings(_env_file=None))

    assert isinstance(provider, MockBrokerProvider)


def test_factory_requires_target_specific_token() -> None:
    settings = Settings(
        _env_file=None,
        broker_provider="tinvest",
        tinvest_target="sandbox",
        tinvest_token="production-only-token",
    )

    with pytest.raises(BrokerConfigurationError, match="token is required"):
        create_broker_provider(settings)
