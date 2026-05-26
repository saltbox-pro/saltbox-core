import asyncio

from redis import asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_sc_service import JobSchemaService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.services.collection import CollectionService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository
from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository
from saltbox_core.tasks.repositories.tasks_template import TaskTemplateRepository
from saltbox_core.tasks.schemas.task import TaskForLifespanModel
from saltbox_core.tasks.schemas.tasks_status import TaskStatus
from saltbox_core.tasks.services.task import TaskService
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_core.tasks.services.tasks_status import TaskStatusService
from saltbox_core.tasks.services.tasks_template import TaskTemplateService
from saltbox_core.tkq import shutdown_broker, startup_broker
from saltbox_sdk.config.redis_config import REDIS_SETTINGS
from saltbox_sdk.db.mongo.config import get_mongo_db


class TasksWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.db = get_mongo_db()

        self.job_repository = JobRepository(self.db)
        self.job_schema_repository = JobSchemaRepository(self.db)
        self.master_repository = MasterRepository(self.db)
        self.collections_repository = CollectionRepository(self.db)
        self.minions_repository = MinionRepository(self.db)
        self.task_repository = TaskRepository(self.db)
        self.task_status_repository = TaskStatusRepository(self.db)
        self.task_minion_repository = TaskMinionRepository(self.db)
        self.task_template_repository = TaskTemplateRepository(self.db)

        logger.info('Tasks watcher started')

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)

        return self.redis

    async def process(self) -> None:
        redis: aioredis.Redis = await self.get_redis()

        job_return_repository = JobReturnRepository(database=self.db, rdb=redis)
        job_return_service = JobReturnService(repo=job_return_repository, rdb=redis)
        job_schema_service = JobSchemaService(repo=self.job_schema_repository)
        master_service = MasterService(repo=self.master_repository)
        job_service = JobService(
            rdb=redis,
            job_repository=self.job_repository,
            job_schema_service=job_schema_service,
            job_return_service=job_return_service,
            master_service=master_service,
        )
        minion_service = MinionService(repo=self.minions_repository)
        collection_service = CollectionService(repo=self.collections_repository)
        task_status_service = TaskStatusService(repo=self.task_status_repository)
        task_template_service = TaskTemplateService(repo=self.task_template_repository)
        task_minion_service = TaskMinionService(repo=self.task_minion_repository, rdb=redis)
        task_service: TaskService = TaskService(
            repo=self.task_repository,
            rdb=redis,
            task_status_service=task_status_service,
            task_template_service=task_template_service,
            task_minion_service=task_minion_service,
            job_schema_service=job_schema_service,
            collections_service=collection_service,
            minion_service=minion_service,
        )

        logger.info('Processing tasks...')

        while True:
            tasks: list[TaskForLifespanModel] = await task_service.get_list(
                query={'status.type': {'$in': [TaskStatus.wait_minions, TaskStatus.running, TaskStatus.stopping]}},
                limit=0,
                skip=0,
                projection_model=TaskForLifespanModel,
            )

            for task in tasks:
                task_lifespan_service = TaskLifespanService(
                    rdb=redis,
                    task_service=task_service,
                    task_minion_service=task_minion_service,
                    master_service=master_service,
                    job_service=job_service,
                    job_return_service=job_return_service,
                    minion_service=minion_service,
                    collection_service=collection_service,
                    task=task,
                )
                await task_lifespan_service.process()  # TODO (i.moshkov): move to celery task

            await asyncio.sleep(1)


async def async_main() -> None:
    logger.info('Starting task watcher')
    watcher = TasksWatcher()

    await startup_broker()
    await watcher.process()
    await shutdown_broker()

    logger.info('Task watcher stopped')


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
