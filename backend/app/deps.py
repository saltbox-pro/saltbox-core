#  from collections.abc import Generator
import redis.asyncio as redis
from typing import Annotated
from fastapi import Depends

from app.config import SETTINGS


def get_redis_db() -> redis.Redis:
    redis_connection_pool: redis.ConnectionPool = \
        redis.ConnectionPool.from_url(SETTINGS.redis_url)
    return redis.Redis(connection_pool=redis_connection_pool)


RedisDep = Annotated[redis.Redis, Depends(get_redis_db)]
