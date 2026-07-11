import asyncio

from redis.asyncio import Redis

from app.core.config import get_settings


async def check() -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        if not await redis.exists("broker-stream:listener:heartbeat"):
            raise RuntimeError("Stream listener heartbeat is missing")
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(check())
