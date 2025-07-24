import asyncio

from redis import asyncio as aioredis

from salt_box_core.db.init_mongo_db import init_mongo_db
from salt_box_core.jobs.repositories.job_repository import JobRepository
from salt_box_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from salt_box_core.jobs.services.job_sc_service import JobSchemaService
from salt_box_core.jobs.services.job_services import JobService
from salt_box_core.masters.repositories.master_repository import MasterRepository
from salt_box_core.masters.services.master_service import MasterService
from salt_box_core.minion_collections.repositories.collection_repository import CollectionRepository
from salt_box_core.minion_collections.repositories.minion_repository import MinionRepository
from salt_box_core.minion_collections.services.collection_service import CollectionService
from salt_box_core.minion_collections.services.minion_service import MinionService
from salt_box_core.tasks.repositories.task_repository import TaskRepository
from salt_box_core.tasks.repositories.task_template_repository import TaskTemplateRepository
from salt_box_core.tasks.schemas.task_schemas import TaskModel, TaskStatus
from salt_box_core.tasks.services.tasks import TaskService
from salt_box_core.tasks.services.tasks_lifespan import TaskLifespanService
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService
from saltbox_sdk.config import REDIS_SETTINGS, logger
from saltbox_sdk.db.mongo.config import get_mongo_db


class TasksWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.db = get_mongo_db()

        self.job_schema_repository = JobSchemaRepository(self.db)
        self.master_repository = MasterRepository(self.db)
        self.collections_repository: CollectionRepository = CollectionRepository(self.db)
        self.minions_repository: MinionRepository = MinionRepository(self.db)
        self.task_repository: TaskRepository = TaskRepository(self.db)
        self.task_template_repository: TaskTemplateRepository = TaskTemplateRepository(self.db)

        logger.info('Tasks watcher started')

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)

        return self.redis

    async def process(self) -> None:
        redis: aioredis.Redis = await self.get_redis()

        job_repository = JobRepository(redis)
        job_schema_service: JobSchemaService = JobSchemaService(repo=self.job_schema_repository)
        master_service: MasterService = MasterService(repo=self.master_repository)
        job_service: JobService = JobService(
            rdb=redis,
            job_repository=job_repository,
            job_schema_service=job_schema_service,
            master_service=master_service,
        )
        minion_service: MinionService = MinionService(repo=self.minions_repository)
        collection_service: CollectionService = CollectionService(repo=self.collections_repository)
        task_template_service: TaskTemplateService = TaskTemplateService(repo=self.task_template_repository)
        task_service: TaskService = TaskService(
            repo=self.task_repository,
            rdb=redis,
            task_template_service=task_template_service,
            job_schema_service=job_schema_service,
            collections_service=collection_service,
        )

        logger.info('Processing tasks...')

        while True:
            tasks: list[TaskModel] = await task_service.get_list(
                query={'status': {'$in': [TaskStatus.running, TaskStatus.stopping, TaskStatus.postprocessing]}},
                limit=0,
                skip=0,
            )

            for task in tasks:
                task_lifespan_service = TaskLifespanService(
                    rdb=redis,
                    task_service=task_service,
                    job_service=job_service,
                    minion_service=minion_service,
                    collection_service=collection_service,
                    task=task,
                )
                await task_lifespan_service.process()  # TODO (i.moshkov): move to celery task

            await asyncio.sleep(1)


async def async_main() -> None:
    logger.info('Starting watcher')

    await init_mongo_db()
    watcher = TasksWatcher()

    await watcher.process()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
