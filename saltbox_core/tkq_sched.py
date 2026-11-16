from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisScheduleSource

from saltbox_core.config import SETTINGS, logger
from saltbox_core.tkq import broker, queue_default, queue_membership, queue_notify, queue_salt
from saltbox_sdk.utilities.taskiq import SaltboxTaskiqScheduler

redis_source = RedisScheduleSource(SETTINGS.taskiq_redis_url)
logger.debug('SETTINGS.taskiq_redis_url: %s', SETTINGS.taskiq_redis_url)

# Without this, kick() routes to "taskiq" (default fallback) instead of the task's queue_name label.
broker.with_queues(queue_default, queue_salt, queue_notify, queue_membership)

scheduler = SaltboxTaskiqScheduler(
    broker,
    [
        # Label schedule source. To schedule tasks with labels.
        LabelScheduleSource(broker),
        # Dynamic schedule source. To add tasks dynamically.
        redis_source,
    ],
)
