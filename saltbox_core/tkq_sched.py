from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisScheduleSource

from saltbox_core.config import SETTINGS, logger
from saltbox_core.tkq import broker

redis_source = RedisScheduleSource(SETTINGS.taskiq_redis_url)
logger.debug('SETTINGS.taskiq_redis_url: %s', SETTINGS.taskiq_redis_url)


scheduler = TaskiqScheduler(
    broker,
    [
        # Label schedule source. To schedule tasks with labels.
        LabelScheduleSource(broker),
        # Dynamic schedule source. To add tasks dynamically.
        redis_source,
    ],
)
