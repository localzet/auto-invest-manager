import asyncio
import sys

from redis.asyncio import Redis

from app.core.config import get_settings


async def check_scheduler() -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        if not await redis.exists("automation:scheduler:heartbeat"):
            raise RuntimeError("Scheduler heartbeat is missing")
    finally:
        await redis.aclose()


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "scheduler":
        raise SystemExit("Usage: python -m app.automation.healthcheck scheduler")
    asyncio.run(check_scheduler())


if __name__ == "__main__":
    main()
