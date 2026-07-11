import asyncio
import signal

from arq import create_pool
from arq.connections import RedisSettings

from app.automation.broker import RetryingBrokerProvider
from app.automation.retry import RetryPolicy
from app.broker.factory import create_broker_provider
from app.core.config import get_settings
from app.notifications.factory import create_notifier
from app.streams.supervisor import BrokerStreamSupervisor


async def run_listener() -> None:
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for exit_signal in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(exit_signal, stop_event.set)
    retry = RetryPolicy(
        settings.broker_retry_max_attempts,
        settings.broker_retry_base_delay_seconds,
        settings.broker_retry_max_delay_seconds,
    )
    broker = RetryingBrokerProvider(create_broker_provider(settings), retry)
    heartbeat_task = asyncio.create_task(_heartbeat(redis, stop_event))
    try:
        await BrokerStreamSupervisor(broker, redis, settings, create_notifier(settings)).run(
            stop_event
        )
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        await redis.delete("broker-stream:listener:heartbeat")
        await redis.aclose()


async def _heartbeat(redis: object, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await redis.set(
            "broker-stream:listener:heartbeat",
            asyncio.get_running_loop().time(),
            ex=90,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30)
        except TimeoutError:
            pass


def main() -> None:
    asyncio.run(run_listener())


if __name__ == "__main__":
    main()
