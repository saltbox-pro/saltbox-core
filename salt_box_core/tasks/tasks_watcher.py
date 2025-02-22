import asyncio
import logging.config

from redis import asyncio as aioredis

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.db.mongo.init_db import init_mongo_db
from salt_box_core.jobs.services import JobService
from salt_box_core.minion_collections.repositories.collection_repository import CollectionRepository
from salt_box_core.minion_collections.repositories.minion_repository import MinionRepository
from salt_box_core.minion_collections.services.collection_service import CollectionService
from salt_box_core.minion_collections.services.minion_service import MinionService
from salt_box_core.schema_sync.repository import JSONSchemaRepository
from salt_box_core.schema_sync.services.schema_service import JSONSchemaService
from salt_box_core.tasks.repositories.task_repository import TaskRepository
from salt_box_core.tasks.repositories.task_template_repository import TaskTemplateRepository
from salt_box_core.tasks.schemas.task_schemas import TaskModel, TaskStatus
from salt_box_core.tasks.services.tasks import TaskService
from salt_box_core.tasks.services.tasks_lifespan import TaskLifespanService
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class TasksWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.db = get_mongo_db()

        self.json_schema_repository = JSONSchemaRepository(self.db)
        self.collections_repository: CollectionRepository = CollectionRepository(self.db)
        self.minions_repository: MinionRepository = MinionRepository(self.db)
        self.task_repository: TaskRepository = TaskRepository(self.db)
        self.task_template_repository: TaskTemplateRepository = TaskTemplateRepository(self.db)

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)

        return self.redis

    async def process(self) -> None:
        redis: aioredis.Redis = await self.get_redis()

        json_schema_service: JSONSchemaService = JSONSchemaService(repo=self.json_schema_repository)
        job_service: JobService = JobService(rdb=redis, json_schema_service=json_schema_service)
        minion_service: MinionService = MinionService(repo=self.minions_repository)
        collection_service: CollectionService = CollectionService(repo=self.collections_repository)
        task_template_service: TaskTemplateService = TaskTemplateService(repo=self.task_template_repository)
        task_service: TaskService = TaskService(
            repo=self.task_repository, rdb=redis, task_template_service=task_template_service
        )

        while True:
            tasks: list[TaskModel] = await task_service.get_list(query={'status': TaskStatus.running}, limit=0, skip=0)

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
    await init_mongo_db()
    watcher = TasksWatcher()

    logger.info('Starting watcher')
    await watcher.process()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
