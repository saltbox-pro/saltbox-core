import logging

from typing import Annotated, AsyncGenerator

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from fastms_core.config import SETTINGS


LOGGER = logging.getLogger(__name__)


def _make_pool() -> ConnectionPool:
    return ConnectionPool.from_url(SETTINGS.redis_url)


POOL = _make_pool()


async def get_redis() -> AsyncGenerator[Redis, None]:
    redis = Redis(connection_pool=POOL)
    yield redis
    LOGGER.debug('Close redis connection now')
    await redis.aclose()


RedisDependency = Annotated[Redis, Depends(get_redis)]
