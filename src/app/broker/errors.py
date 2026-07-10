class BrokerError(Exception):
    """Base exception for broker integration failures."""


class BrokerConfigurationError(BrokerError):
    """Raised when broker integration configuration is invalid."""


class InstrumentNotFoundError(BrokerError):
    """Raised when an instrument cannot be resolved unambiguously."""


class BrokerTemporaryError(BrokerError):
    """Raised when a safe broker read can be retried."""


class BrokerRateLimitError(BrokerTemporaryError):
    """Raised when the broker asks the client to retry later."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
