import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress

import taskiq_fastapi
from aio_pika.abc import ExchangeType
from aiormq import AMQPConnectionError
from redis.asyncio import Redis
from taskiq import AsyncBroker, Context, TaskiqDepends
from taskiq.exceptions import NoResultError
from taskiq_aio_pika import AioPikaBroker, Exchange, Queue, QueueType
from taskiq_redis import RedisAsyncResultBackend

from saltbox_core.config import SETTINGS
from saltbox_sdk.config.rabbitmq_config import RABBIT_SETTINGS
from saltbox_sdk.utilities.taskiq import SmartRetryMiddleware, UniqueIdMiddleware

logger = logging.getLogger(__name__)

result_backend: RedisAsyncResultBackend = RedisAsyncResultBackend(SETTINGS.taskiq_redis_url)
broker = (
    AioPikaBroker(
        url=RABBIT_SETTINGS.url,
        exchange=Exchange(
            name='topic_exchange',
            type=ExchangeType.TOPIC,
        ),
        delay_queue=Queue(
            name='taskiq.delay',
            routing_key='queue-default',
        ),
    )
    .with_result_backend(result_backend)
    .with_middlewares(
        UniqueIdMiddleware(),
        SmartRetryMiddleware(
            default_retry_count=SETTINGS.taskiq_retry_default_retry_count,
            default_retry_label=SETTINGS.taskiq_retry_default_retry_label,
            no_result_on_retry=SETTINGS.taskiq_retry_no_result_on_retry,
            default_delay=SETTINGS.taskiq_retry_default_delay,
            use_jitter=SETTINGS.taskiq_retry_use_jitter,
            use_delay_exponent=SETTINGS.taskiq_retry_use_delay_exponent,
            max_delay_exponent=SETTINGS.taskiq_retry_max_delay_exponent,
        ),
    )
    .with_id_generator(lambda: uuid.uuid4().hex)
)


queue_common = Queue(
    name='queue-common',
    type=QueueType.CLASSIC,
    durable=False,
)  # TODO (@): Temporary!!! This queue for fix bug https://github.com/taskiq-python/taskiq-aio-pika/issues/51
queue_default = Queue(
    name='queue-default',
    type=QueueType.CLASSIC,
    durable=False,
)
queue_salt = Queue(
    name='queue-salt',
    type=QueueType.CLASSIC,
    durable=False,
)
queue_notify = Queue(
    name='queue-notify',
    type=QueueType.CLASSIC,
    durable=False,
)


async def startup_broker() -> AsyncBroker:
    if not broker.is_worker_process:
        try:
            broker.with_queues(queue_default, queue_salt, queue_notify)
            await broker.startup()
        except AMQPConnectionError as ex:
            logger.warning(
                f'RabbitMQ is unavailable during startup: {ex}. '
                'The broker will reconnect automatically.'
            )
    return broker


async def shutdown_broker() -> AsyncBroker:
    if not broker.is_worker_process:
        try:
            await broker.shutdown()
        except AMQPConnectionError as ex:
            logger.warning(
                f'RabbitMQ is unavailable during startup: {ex}. '
                'The broker will reconnect automatically.'
            )
    return broker


def broker_for_default_worker() -> AioPikaBroker:
    logger.info('Starting default broker')
    return broker.with_queues(queue_common, queue_default)


def broker_for_salt_worker() -> AioPikaBroker:
    logger.info('Starting salt broker')
    return broker.with_queues(queue_common, queue_salt)


def broker_for_notify_worker() -> AioPikaBroker:
    logger.info('Starting notify broker')
    return broker.with_queues(queue_common, queue_notify)


taskiq_fastapi.init(broker, 'saltbox_core.main:app')


async def get_result_backend_redis_connection() -> AsyncGenerator[Redis]:
    async with Redis(connection_pool=result_backend.redis_pool) as redis:
        with suppress(NoResultError):
            yield redis


# https://github.com/orgs/taskiq-python/discussions/132
class ConcurrencyLocker:
    """
    Taskiq dependency to ensure monopoly task execution.

    If task will be "kiqed" again while executing, it will be queued to execute only once
    after the current run.

    Attrubutes:
        name (str | None): optional explicit task name
        expire (int | None): optional expiration time for every retry
    """

    REQUEUE_DELAY_SEC = 1
    # Taskiq has `X-Taskiq-requeue` label, but we can not be sure it is stable
    LABEL_REQUEUED = 'SB-Requeued'

    def __init__(self, expire: int | None = None, name: str | None = None) -> None:
        self.name = name
        self.expire = expire

    async def __call__(
        self,
        redis: Redis = TaskiqDepends(get_result_backend_redis_connection),
        context: Context = TaskiqDepends(),
    ) -> AsyncGenerator[None, None]:
        name = self.name or context.message.task_name
        counter_name = f'{name}_COUNTER'

        async with redis.pipeline(transaction=True) as pipe:
            pipe = pipe.incr(counter_name)
            if self.expire is not None:
                pipe = pipe.expire(name=counter_name, time=self.expire)
            pipe = pipe.get(name=counter_name)
            result = await pipe.execute()

        current_val = int(result[-1])
        logger.debug('ConcurrencyLocker %s counter: %i', counter_name, current_val)

        if current_val > 1 and context.message.labels.get(self.LABEL_REQUEUED):
            await redis.decr(counter_name)
            await context.requeue()

        if current_val == 2:
            logger.info('ConcurrencyLocker requeues task because seems already in progress: %s', name)
            context.message.labels['delay'] = str(self.REQUEUE_DELAY_SEC)
            context.message.labels[self.LABEL_REQUEUED] = str(True)
            await context.requeue()
        if current_val > 2:
            logger.info('ConcurrencyLocker rejects task because seems already requeued: %s', counter_name)
            # Reject the task.
            # Idea was to use context.reject(), but as for taskqik==0.11.17 it raises TaskRejectedError,
            # which can not be handled in dependency.
            raise NoResultError()

        try:
            yield
        finally:
            await redis.delete(counter_name)
