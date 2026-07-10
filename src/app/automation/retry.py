import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from app.broker.errors import BrokerRateLimitError, BrokerTemporaryError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 20.0
    jitter: bool = True

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await operation()
            except Exception as error:
                code = _error_code(error)
                retryable = isinstance(
                    error, (BrokerTemporaryError, TimeoutError, ConnectionError, OSError)
                ) or code in {"UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"}
                if not retryable:
                    raise
                if attempt >= self.max_attempts:
                    if code == "RESOURCE_EXHAUSTED":
                        raise BrokerRateLimitError(
                            "Broker read rate limit exceeded",
                            _retry_after_seconds(error),
                        ) from error
                    raise
                delay = min(
                    self.max_delay_seconds,
                    self.base_delay_seconds * (2 ** (attempt - 1)),
                )
                if isinstance(error, BrokerRateLimitError) and error.retry_after_seconds:
                    delay = min(self.max_delay_seconds, error.retry_after_seconds)
                elif retry_after := _retry_after_seconds(error):
                    delay = min(self.max_delay_seconds, retry_after)
                if self.jitter:
                    delay = random.uniform(0, delay)
                await asyncio.sleep(delay)
        raise RuntimeError("Retry policy exhausted unexpectedly")


def _error_code(error: Exception) -> str | None:
    code_method = getattr(error, "code", None)
    if not callable(code_method):
        return None
    code = code_method()
    return getattr(code, "name", str(code).rsplit(".", 1)[-1])


def _retry_after_seconds(error: Exception) -> float | None:
    direct = getattr(error, "retry_after_seconds", None)
    if isinstance(direct, int | float) and direct > 0:
        return float(direct)
    metadata_method = getattr(error, "trailing_metadata", None)
    if not callable(metadata_method):
        return None
    for key, value in metadata_method() or ():
        if str(key).lower() in {"retry-after", "retry-after-ms"}:
            delay = float(value)
            return delay / 1000 if str(key).lower().endswith("-ms") else delay
    return None
