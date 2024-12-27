import asyncio
import logging.config

from redis import asyncio as aioredis

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.config import init_mongo
from fastms_core.tasks.models import Task

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
        while True:
            redis = await self.get_redis()
            tasks = await Task.find({'status': Task.TaskStatus.running}).to_list()

            for task in tasks:
                await task.process(redis=redis)  # TODO: move to celery task

            await asyncio.sleep(1)


async def async_main():
    mongo_client = await init_mongo()
    watcher = TasksWatcher()

    logger.info('Starting watcher')
    await watcher.process()

    mongo_client.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
