import asyncio
from datetime import datetime
from typing import Any

from redis import asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnForJobWatcherSchema, JobReturnStatus
from saltbox_core.jobs.schemas.job_schemas import JobStatus
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.pillars.repository import get_pillar_repository
from saltbox_core.task_templates.repositories.template import TaskTemplateRepository
from saltbox_core.task_templates.services.template import TaskTemplateService
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository
from saltbox_core.tasks.schemas.task import TaskForStatusUpdateSchema
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionForTaskStatusUpdateSchema, TaskMinionStatus
from saltbox_core.tasks.services.task import TaskService
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_core.tasks.services.tasks_status import TaskStatusService
from saltbox_core.tkq import shutdown_broker, startup_broker
from saltbox_sdk.config.redis_config import REDIS_SETTINGS
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.exceptions import MultipleObjectsFoundException, ObjectNotFoundException
from saltbox_sdk.utilities.helpers import utc_now


class JobsWatcher:
    def __init__(self, redis: aioredis.Redis) -> None:
        db = get_mongo_db()

        extra_data_category_repository = ExtraDataCategoryRepository(db)
        extra_data_repository = ExtraDataRepository(db, extra_data_category_repository=extra_data_category_repository)
        collection_repository = CollectionRepository(db)
        task_status_service = TaskStatusService(repo=TaskStatusRepository(db))
        task_template_service = TaskTemplateService(
            repo=TaskTemplateRepository(db), pillar_repo=get_pillar_repository(db=db)
        )

        self.job_return_service = JobReturnService(repo=JobReturnRepository(database=db, rdb=redis), rdb=redis)
        self.task_minion_service = TaskMinionService(repo=TaskMinionRepository(db), rdb=redis)
        self.job_service = JobService(
            rdb=redis,
            job_repository=JobRepository(db),
            job_return_service=self.job_return_service,
            task_template_service=task_template_service,
            master_service=MasterService(repo=MasterRepository(db)),
        )
        self.task_service = TaskService(
            repo=TaskRepository(db),
            rdb=redis,
            task_status_service=task_status_service,
            task_template_service=task_template_service,
            task_minion_service=self.task_minion_service,
            collections_service=CollectionService(repo=collection_repository),
            minion_service=MinionService(
                repo=MinionRepository(
                    db, extra_data_repository=extra_data_repository, collection_repository=collection_repository
                )
            ),
            job_service=self.job_service,
        )

    async def timeout_job_return(self, job_return: JobReturnForJobWatcherSchema) -> None:
        try:
            await self.job_return_service.update(
                query={'_id': job_return.id, 'status': JobReturnStatus.waiting},
                data={'status': JobReturnStatus.timeout},
            )
        except ObjectNotFoundException:
            return

        logger.debug(f'Job: #{job_return.jid} for minion {job_return.minion_id} is timeout')

        if job_return.source and job_return.source.type == 'task' and job_return.source.id:
            logger.debug(f'Task job has timeout job {job_return.source.id} for minion {job_return.minion_id}')

            try:
                task = await self.task_service.get(
                    query=PyObjectId(job_return.source.id), projection_model=TaskForStatusUpdateSchema
                )
                task_minion = await self.task_minion_service.get(
                    query={
                        'task_id': task.id,
                        'minion_id': job_return.minion_id,
                        'master': job_return.salt_master,
                        'status': {'$ne': TaskMinionStatus.pending},
                    },
                    projection_model=TaskMinionForTaskStatusUpdateSchema,
                )

                data_to_update: dict[str, Any] = {}

                if task_minion.count_runs >= task.max_retries:
                    data_to_update['status'] = TaskMinionStatus.failed
                    data_to_update['finished_dt'] = utc_now()
                else:
                    data_to_update['status'] = TaskMinionStatus.pending

                await self.task_minion_service.update(query=task_minion.id, data=data_to_update)
                await self.task_service.update(query=task.id, data={})
            except (ObjectNotFoundException, MultipleObjectsFoundException) as e:
                logger.warning(
                    f'Cannot update task minion of task {job_return.source.id} '
                    f'for minion {job_return.minion_id} on timeout: {e}'
                )

    async def finish_completed_jobs(self, job_ids: set[PyObjectId]) -> None:
        if not job_ids:
            return

        job_ids_to_finish = job_ids - await self.job_return_service.get_job_ids_by_return_status(
            job_ids=job_ids, status=JobReturnStatus.waiting
        )

        if not job_ids_to_finish:
            return

        await self.job_service.bulk_update(
            query={'_id': {'$in': list(job_ids_to_finish)}, 'status': JobStatus.running},
            data={'status': JobStatus.finished},
        )

    async def process_expired_jobs(self, now: datetime) -> None:
        jobs = await self.job_service.get_list(
            query={'status': JobStatus.running, 'waiting_expires_at_dt': {'$lt': now}},
            projection_model=EmptyModel,
        )

        job_ids: set[PyObjectId] = set()

        for job in jobs:
            job_returns = await self.job_return_service.get_list(
                query={'job_id': job.id, 'status': JobReturnStatus.waiting, 'ttl': None},
                projection_model=JobReturnForJobWatcherSchema,
            )

            for job_return in job_returns:
                await self.timeout_job_return(job_return)

            job_ids.add(job.id)

        await self.finish_completed_jobs(job_ids)

    async def process_expired_job_returns(self, now: datetime) -> None:
        job_returns = await self.job_return_service.get_list(
            query={
                'status': JobReturnStatus.waiting,
                'ttl': {'$ne': None},
                'waiting_expires_at_dt': {'$lt': now},
            },
            projection_model=JobReturnForJobWatcherSchema,
        )

        job_ids: set[PyObjectId] = set()

        for job_return in job_returns:
            await self.timeout_job_return(job_return)
            job_ids.add(job_return.job_id)

        await self.finish_completed_jobs(job_ids)

    async def process(self) -> None:
        logger.info('Processing jobs...')

        while True:
            now = utc_now()

            await self.process_expired_jobs(now)
            await self.process_expired_job_returns(now)

            await asyncio.sleep(1)


async def async_main() -> None:
    logger.info('Starting jobs watcher')
    redis = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)
    watcher = JobsWatcher(redis=redis)

    await startup_broker()
    await watcher.process()
    await shutdown_broker()

    logger.info('Jobs watcher finished')


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
