import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from salt_box_core.config import SETTINGS

LOGGER = logging.getLogger(__name__)


def _make_pool() -> ConnectionPool:
    return ConnectionPool.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)


POOL = _make_pool()


def get_redis_now() -> Redis:
    return Redis(connection_pool=POOL)


async def get_redis() -> AsyncGenerator[Redis, None]:
    redis = Redis(connection_pool=POOL)
    yield redis
    LOGGER.debug('Close redis connection now')
    await redis.aclose()  # type: ignore[attr-defined]


RedisDependency = Annotated[Redis, Depends(get_redis)]


def get_redis_dep(redis: RedisDependency) -> Redis:
    return redis
