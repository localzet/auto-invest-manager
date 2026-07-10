from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis

RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class LockLease:
    key: str
    owner_token: str


class RedisCycleLock:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def acquire(self, account_id: str) -> LockLease | None:
        key = f"automation-cycle:{account_id}"
        owner_token = uuid4().hex
        acquired = await self._redis.set(key, owner_token, nx=True, ex=self._ttl_seconds)
        return LockLease(key, owner_token) if acquired else None

    async def release(self, lease: LockLease) -> bool:
        released = await self._redis.eval(RELEASE_SCRIPT, 1, lease.key, lease.owner_token)
        return bool(released)
