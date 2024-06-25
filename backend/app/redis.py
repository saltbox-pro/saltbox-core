import logging

from typing import Annotated

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from app.config import SETTINGS


LOGGER = logging.getLogger(__name__)


def _make_pool() -> ConnectionPool:
    return ConnectionPool.from_url(SETTINGS.redis_url)


POOL = _make_pool()


def get_redis_db() -> Redis:
    return Redis(connection_pool=POOL)


RedisDep = Annotated[Redis, Depends(get_redis_db)]
