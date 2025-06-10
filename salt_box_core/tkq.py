import logging
from collections.abc import AsyncGenerator
from contextlib import suppress

import taskiq_fastapi
from redis.asyncio import Redis
from taskiq import Context, TaskiqDepends
from taskiq.exceptions import NoResultError
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend

from salt_box_core.config import SETTINGS

logger = logging.getLogger(__name__)
result_backend: RedisAsyncResultBackend = RedisAsyncResultBackend(SETTINGS.taskiq_redis_url)
broker = AioPikaBroker(SETTINGS.rabbitmq_url)\
    .with_result_backend(result_backend)


taskiq_fastapi.init(broker, 'salt_box_core.main:app')


async def get_result_backend_redis_connection() -> AsyncGenerator[Redis]:
    async with Redis(connection_pool=result_backend.redis_pool) as redis:
        with suppress(NoResultError):
            yield redis


# https://github.com/orgs/taskiq-python/discussions/132
class ConcurrencyLimiter:
    # TODO Docstring
    """
    """
    REQUEUE_DELAY_SEC = 1

    def __init__(self, limit: int, expire: int | None = None, name: str | None = None) -> None:
        self.limit = limit
        self.name = name
        self.expire = expire

    async def __call__(
        self,
        redis: Redis = TaskiqDepends(get_result_backend_redis_connection),
        context: Context = TaskiqDepends(),
    ) -> AsyncGenerator[None, None]:
        counter_name = f'{self.name or context.message.task_name}_CONCURRENCY_LIMIT'
        current_val = int(await redis.get(counter_name) or 0)
        logger.debug('ConcurrencyLimiter %s current limit: %i', counter_name, current_val)

        if current_val >= self.limit:
            logger.info('ConcurrencyLimiter %s limit is reached', counter_name)
            context.message.labels['delay'] = str(self.REQUEUE_DELAY_SEC)
            # TODO REJECT
            #raise NoResultError()
            #context.reject()
            await context.requeue()

        async with redis.pipeline(transaction=True) as pipe:
            pipe = pipe.incr(counter_name)
            pipe = pipe.expire(name=counter_name, time=360)
            await pipe.execute()

        try:
            yield
        finally:
            await redis.decr(counter_name)
