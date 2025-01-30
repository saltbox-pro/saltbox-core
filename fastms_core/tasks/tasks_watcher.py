import asyncio
import logging.config

from redis import asyncio as aioredis

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.init_db import init_mongo_db
from fastms_core.jobs.services import JobService
from fastms_core.tasks.schemas import TaskSchema
from fastms_core.tasks.services import TaskLifespanService, TaskService, TaskTemplateService

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class TasksWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None

    async def get_redis(self) -> aioredis.Redis:
        if self.redis is None:
            self.redis = await aioredis.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)

        return self.redis

    async def process(self) -> None:
        redis = await self.get_redis()

        job_service = JobService(rdb=redis)
        task_template_service = TaskTemplateService(rdb=redis)
        task_service = TaskService(rdb=redis, task_template_service=task_template_service)

        while True:

            tasks: list[TaskSchema] = await task_service.get_list(
                query={'status': TaskSchema.TaskStatus.running},
                projection_schema=TaskSchema
            )

            for task in tasks:
                task_lifespan_service = TaskLifespanService(
                    rdb=redis,
                    task_service=task_service,
                    job_service=job_service,
                    task=task
                )
                await task_lifespan_service.process()  # TODO: move to celery task

            await asyncio.sleep(1)


async def async_main():
    await init_mongo_db()
    watcher = TasksWatcher()

    logger.info('Starting watcher')
    await watcher.process()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
