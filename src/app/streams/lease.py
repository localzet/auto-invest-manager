from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis

RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class StreamLease:
    key: str
    owner_token: str


class RedisStreamLease:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def acquire(self, key: str) -> StreamLease | None:
        owner = uuid4().hex
        acquired = await self._redis.set(key, owner, nx=True, ex=self._ttl_seconds)
        return StreamLease(key, owner) if acquired else None

    async def renew(self, lease: StreamLease) -> bool:
        return bool(
            await self._redis.eval(RENEW_SCRIPT, 1, lease.key, lease.owner_token, self._ttl_seconds)
        )

    async def release(self, lease: StreamLease) -> bool:
        return bool(await self._redis.eval(RELEASE_SCRIPT, 1, lease.key, lease.owner_token))
