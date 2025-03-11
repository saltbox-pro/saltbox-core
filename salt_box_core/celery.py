from datetime import UTC, timedelta
from typing import Any, ClassVar

from celery import Celery
from salt_box_core.config import APP_NAME, SETTINGS


class CeleryConfig:
    accept_content: ClassVar[list[str]] = ['json']
    beat_schedule: ClassVar[dict] = {}
    beat_schedule_filename = SETTINGS.celery_beat_schedule_filename
    broker_connection_retry_on_startup = True
    broker_url = SETTINGS.celery_broker_url
    # result_backend = SETTINGS.celery_broker_url
    result_backend = SETTINGS.mongo_url
    mongodb_backend_settings: ClassVar[dict] = {
        'database': SETTINGS.mongo_db,
        'taskmeta_collection': 'celery_taskmeta',
    }
    result_serializer = 'json'
    enable_utc = True
    result_expires = timedelta(minutes=60)
    # TODO (a.karmanov): May be useful to pass tests.
    # task_always_eager = True
    task_create_missing_queues = True
    task_default_exchange = 'tasks'
    task_default_exchange_type = 'topic'
    task_default_priority = 5
    task_default_queue = 'default'
    task_default_routing_key = 'def.other'
    task_ignore_result = False
    task_queue_max_priority = 10
    task_queues: Any = None
    task_routes: ClassVar[dict] = {}
    task_serializer = 'json'
    timezone = UTC
    worker_pool_restarts = True
    worker_prefetch_multiplier = 0
    worker_send_task_events = True


celery = Celery(APP_NAME)
celery.config_from_object(CeleryConfig)
celery.autodiscover_tasks(['salt_box_core.settings', 'salt_box_core.jobs'])
