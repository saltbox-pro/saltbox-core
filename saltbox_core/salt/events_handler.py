import json

from redis import asyncio as aioredis

from saltbox_core.config import SETTINGS, logger
from saltbox_core.jobs.repositories.job_repository import get_job_repository
from saltbox_core.jobs.repositories.job_return_repository import get_job_return_repository
from saltbox_core.jobs.repositories.job_sc_repository import get_job_schema_repository
from saltbox_core.jobs.services.job_return_service import get_job_return_service
from saltbox_core.jobs.services.job_sc_service import get_job_schema_service
from saltbox_core.jobs.services.job_services import get_job_service
from saltbox_core.masters.repositories.master_repository import get_master_repository
from saltbox_core.masters.services.master_service import get_master_service
from saltbox_core.minion_collections.repositories.collection_repository import get_collection_repository
from saltbox_core.minion_collections.repositories.minion_repository import get_minion_repository
from saltbox_core.minion_collections.services.collection_service import get_collection_service
from saltbox_core.minion_collections.services.minion_service import get_minion_service
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler
from saltbox_core.salt.handlers.job_return_handler import JobReturnMessageHandler
from saltbox_core.salt.handlers.metrics_handler import SaltMessageMetricMessageHandler
from saltbox_core.salt.handlers.minion_started_handler import MinionStartedMessageHandler
from saltbox_core.salt.handlers.new_job_handler import JobNewMessageHandler
from saltbox_core.salt.handlers.presence_handler import PresenceMessageHandler
from saltbox_core.tasks.repositories.task_repository import get_task_repository
from saltbox_core.tasks.repositories.task_template_repository import get_task_template_repository
from saltbox_core.tasks.services.tasks import get_task_service
from saltbox_core.tasks.services.tasks_templates import get_task_template_service
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.redis.config import get_redis_now


class SaltEventsHandler:
    BUFFER_LIST_PATTERN = 'salt-events:{master_id}:to_process'

    def __init__(self) -> None:
        self.redis: aioredis.Redis = get_redis_now()
        self.mongo_db = get_mongo_db()
        self.master_repository = get_master_repository(db=self.mongo_db)
        self.master_service = get_master_service(repo=self.master_repository)
        self.minion_repository = get_minion_repository(db=self.mongo_db)
        self.minion_service = get_minion_service(repo=self.minion_repository)
        self.collection_repository = get_collection_repository(db=self.mongo_db)
        self.collection_service = get_collection_service(repo=self.collection_repository)
        self.job_schema_repository = get_job_schema_repository(db=self.mongo_db)
        self.job_schema_service = get_job_schema_service(repo=self.job_schema_repository)
        self.job_return_repository = get_job_return_repository(db=self.mongo_db, rdb=self.redis)
        self.job_return_service = get_job_return_service(rdb=self.redis, repo=self.job_return_repository)
        self.job_repository = get_job_repository(db=self.mongo_db)
        self.job_service = get_job_service(
            rdb=self.redis,
            job_repository=self.job_repository,
            job_schema_service=self.job_schema_service,
            master_service=self.master_service,
        )
        self.task_template_repository = get_task_template_repository(db=self.mongo_db)
        self.task_template_service = get_task_template_service(repo=self.task_template_repository)
        self.task_repository = get_task_repository(db=self.mongo_db)
        self.task_service = get_task_service(
            repo=self.task_repository,
            rdb=self.redis,
            task_template_service=self.task_template_service,
            job_schema_service=self.job_schema_service,
            collections_service=self.collection_service,
        )

        self.salt_handlers: list[BaseMessageHandler] = [
            SaltMessageMetricMessageHandler(redis_client=self.redis),
            JobNewMessageHandler(redis_client=self.redis, job_service=self.job_service),
            JobReturnMessageHandler(
                redis_client=self.redis,
                job_service=self.job_service,
                job_return_service=self.job_return_service,
                minion_service=self.minion_service,
            ),
            PresenceMessageHandler(redis_client=self.redis, minion_service=self.minion_service),
            MinionStartedMessageHandler(redis_client=self.redis, job_service=self.job_service),
        ]

    async def push_failed_event(self, master_id: str, tag: str, data: dict, retries: int) -> None:
        retries += 1

        if retries >= SETTINGS.salt_buffer_manager_event_process_retries:
            logger.error(
                f'Event "{tag}" from master "{master_id}" has max retries ({retries}) exceeded and will be skipped: \n'
                f'{data}'
            )
        else:
            await self.redis.lpush(
                self.BUFFER_LIST_PATTERN.format(master_id=master_id),
                json.dumps({'master_id': master_id, 'tag': tag, 'data': data, 'retries': retries}),
            )

    async def process_event(self, master_id: str, tag: str, data: dict, retries: int) -> None:
        logger.debug('Processing salt event for master "%s" with tag "%s"', master_id, tag)

        for handler in self.salt_handlers:
            try:
                await handler.handle(master_id=master_id, tag=tag, data=data)
            except StopProcessing:
                break
            except Exception as e:
                logger.debug('Process salt event failed: %s', str(e))
                await self.push_failed_event(master_id=master_id, tag=tag, data=data, retries=retries)
                break


salt_events_handler = SaltEventsHandler()
