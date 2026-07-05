from app.broker.interface import BrokerProvider
from app.broker.mock import MockBrokerProvider
from app.broker.tinvest import TInvestClient
from app.core.config import Settings


def create_broker_provider(settings: Settings) -> BrokerProvider:
    if settings.broker_provider == "mock":
        return MockBrokerProvider()
    if settings.tinvest_target == "sandbox":
        token = settings.tinvest_sandbox_token
        endpoint = "sandbox-invest-public-api.tinkoff.ru:443"
    else:
        token = settings.tinvest_token
        endpoint = "invest-public-api.tinkoff.ru:443"
    return TInvestClient(token.get_secret_value() if token else "", endpoint)
