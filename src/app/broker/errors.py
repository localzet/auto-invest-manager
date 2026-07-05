class BrokerError(Exception):
    """Base exception for broker integration failures."""


class BrokerConfigurationError(BrokerError):
    """Raised when broker integration configuration is invalid."""


class InstrumentNotFoundError(BrokerError):
    """Raised when an instrument cannot be resolved unambiguously."""
