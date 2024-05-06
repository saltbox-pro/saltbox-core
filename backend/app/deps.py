#  from collections.abc import Generator
import redis.asyncio as redis
from typing import Annotated
from fastapi import Depends

redis_connection_pool = redis.ConnectionPool.from_url("redis://fastms-redis:6379/0")


def get_redis_db() -> redis.Redis:
    return redis.Redis(connection_pool=redis_connection_pool)


RedisDep = Annotated[redis.Redis, Depends(get_redis_db)]
