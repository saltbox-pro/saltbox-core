import taskiq_fastapi
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend

from salt_box_core.config import SETTINGS

# result_backend: RedisAsyncResultBackend = RedisAsyncResultBackend(SETTINGS.taskiq_redis_url)

broker = AioPikaBroker(SETTINGS.rabbitmq_url).with_result_backend(RedisAsyncResultBackend(SETTINGS.taskiq_redis_url))


taskiq_fastapi.init(broker, 'salt_box_core.main:APP')
