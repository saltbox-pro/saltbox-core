import asyncio
from typing import Any

from redis import asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnForJobWatcherSchema, JobReturnStatus
from saltbox_core.jobs.schemas.job_schemas import JobJidOnlySchema, JobStatus
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_sc_service import JobSchemaService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.minion_collections.repositories.collection_repository import CollectionRepository
from saltbox_core.minion_collections.repositories.minion_repository import MinionRepository
from saltbox_core.minion_collections.services.collection_service import CollectionService
from saltbox_core.minion_collections.services.minion_service import MinionService
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository
from saltbox_core.tasks.repositories.tasks_template import TaskTemplateRepository
from saltbox_core.tasks.schemas.task import TaskForStatusUpdateSchema
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionForTaskStatusUpdateSchema, TaskMinionStatus
from saltbox_core.tasks.services.task import TaskService
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_core.tasks.services.tasks_status import TaskStatusService
from saltbox_core.tasks.services.tasks_template import TaskTemplateService
from saltbox_core.tkq import shutdown_broker, startup_broker
from saltbox_sdk.config.redis_config import REDIS_SETTINGS
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.utilities.helpers import utc_now


class JobsWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.db = get_mongo_db()

        self.job_repository = JobRepository(self.db)
        self.job_schema_repository = JobSchemaRepository(self.db)
        self.minion_repository = MinionRepository(self.db)
        self.collection_repository = CollectionRepository(self.db)
        self.task_minion_repository = TaskMinionRepository(self.db)
        self.task_status_repository = TaskStatusRepository(self.db)
        self.task_template_repository = TaskTemplateRepository(self.db)
        self.task_repository = TaskRepository(self.db)
        self.task_repository = TaskRepository(self.db)
        self.master_repository = MasterRepository(self.db)

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)

        return self.redis

    async def process(self) -> None:
        redis: aioredis.Redis = await self.get_redis()

        job_return_repository = JobReturnRepository(database=self.db, rdb=redis)
        job_return_service = JobReturnService(repo=job_return_repository, rdb=redis)
        job_schema_service = JobSchemaService(repo=self.job_schema_repository)
        task_minion_service = TaskMinionService(repo=self.task_minion_repository, rdb=redis)
        task_status_service = TaskStatusService(repo=self.task_status_repository)
        task_template_service = TaskTemplateService(repo=self.task_template_repository)
        collections_service = CollectionService(repo=self.collection_repository)
        minion_service = MinionService(repo=self.minion_repository)
        task_service = TaskService(
            repo=self.task_repository,
            rdb=redis,
            task_status_service=task_status_service,
            task_template_service=task_template_service,
            task_minion_service=task_minion_service,
            job_schema_service=job_schema_service,
            collections_service=collections_service,
            minion_service=minion_service,
        )
        master_service = MasterService(repo=self.master_repository)
        job_service = JobService(
            rdb=redis,
            job_repository=self.job_repository,
            job_schema_service=job_schema_service,
            job_return_service=job_return_service,
            master_service=master_service,
        )

        logger.info('Processing jobs...')

        while True:
            jobs = await job_service.get_list(
                query={
                    'status': JobStatus.running,
                    'waiting_expires_at_dt': {'$lt': utc_now()},
                },
                projection_model=JobJidOnlySchema,
            )

            for job in jobs:
                job_returns = await job_return_service.get_list(
                    query={'jid': job.jid, 'status': JobReturnStatus.waiting},
                    projection_model=JobReturnForJobWatcherSchema,
                )

                for job_return in job_returns:
                    logger.debug(f'Job: #{job_return.jid} for minion {job_return.minion_id} is timeout')

                    if job_return.source and job_return.source.type == 'task' and job_return.source.id:
                        logger.debug(
                            f'Task job has timeout job {job_return.source.id} for minion {job_return.minion_id}'
                        )

                        try:
                            task = await task_service.get(
                                query=PyObjectId(job_return.source.id), projection_model=TaskForStatusUpdateSchema
                            )
                            task_minion = await task_minion_service.get(
                                query={
                                    'task_id': task.id,
                                    'minion_id': job_return.minion_id,
                                    'master': job_return.salt_master,
                                    'status': {'ne': TaskMinionStatus.pending},
                                },
                                projection_model=TaskMinionForTaskStatusUpdateSchema,
                            )

                            data_to_update: dict[str, Any] = {}

                            if task_minion.count_runs >= task.max_retries:
                                data_to_update['status'] = TaskMinionStatus.failed
                                data_to_update['finished_dt'] = utc_now()
                            else:
                                data_to_update['status'] = TaskMinionStatus.pending

                            await task_minion_service.update(query=task_minion.id, data=data_to_update)
                            await task_service.update(query=task.id, data={})
                        except ObjectNotFoundException:
                            ...

                    await job_return_service.update(query=job_return.id, data={'status': JobReturnStatus.timeout})

                await job_service.update(query=job.id, data={'status': JobStatus.finished})

            await asyncio.sleep(1)


async def async_main() -> None:
    logger.info('Starting jobs watcher')
    watcher = JobsWatcher()

    await startup_broker()
    await watcher.process()
    await shutdown_broker()

    logger.info('Jobs watcher finished')


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
