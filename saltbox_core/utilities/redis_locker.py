from redis.asyncio import Redis
from redis.asyncio.lock import Lock


class AsyncRedisLockFactory:
    """Factory for native Redis locks"""

    def __init__(self, rdb: Redis, ttl: int, prefix: str | None = None) -> None:
        self._redis = rdb
        self._ttl = ttl
        self._prefix = prefix

    def create(self, key: str) -> Lock:
        """Create a new Redis lock instance using redis-py's built-in lock mechanism"""
        full_key = f'lock:{self._prefix}:{key}' if self._prefix else f'lock:{key}'
        return self._redis.lock(full_key, timeout=self._ttl)
