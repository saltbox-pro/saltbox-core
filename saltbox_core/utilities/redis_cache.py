import json
from typing import Any

from redis.asyncio import Redis

from saltbox_core.config import logger


class CustomRedisCache:
    """Custom Redis cache class."""

    def __init__(self, redis: Redis, namespace: str, ttl: int = 3600) -> None:
        self.redis = redis
        self.namespace = namespace
        self.ttl = ttl

    async def _format_key(self, key: str) -> str:
        """Format the key with the namespace."""
        return f'cache:{self.namespace}:{key}'

    async def get(self, key: str) -> Any:
        key = await self._format_key(key)
        return await self.redis.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        key = await self._format_key(key)
        ttl = ttl or self.ttl
        if isinstance(value, dict):
            value = json.dumps(value)
        await self.redis.setex(key, ttl, value)

    @classmethod
    async def clear_cache(cls, redis: Redis, namespace: str | None = None) -> None:
        """Clear the cache for the given namespace or all namespaces."""
        if namespace:
            keys = await redis.keys(f'cache:{namespace}:*')
        else:
            keys = await redis.keys('cache:*')
        if keys:
            await redis.delete(*keys)
            logger.debug('Cache cleared for `%s` namespace', namespace or 'all')
