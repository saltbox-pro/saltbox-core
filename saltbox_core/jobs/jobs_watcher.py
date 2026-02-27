import asyncio

from redis import asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_repository import JobRepository
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnStatus
from saltbox_core.jobs.schemas.job_schemas import JobSimpleSchema, JobStatus
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_sc_service import JobSchemaService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.masters.services.master_service import MasterService
from saltbox_sdk.config.redis_config import REDIS_SETTINGS
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import EmptyModel
from saltbox_sdk.utilities.helpers import utc_now


class JobsWatcher:
    def __init__(self) -> None:
        self.redis: aioredis.Redis | None = None
        self.db = get_mongo_db()

        self.job_repository = JobRepository(self.db)
        self.job_schema_repository = JobSchemaRepository(self.db)
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
                projection_model=JobSimpleSchema,
            )

            for job in jobs:
                logger.info(f'Job: #{job.jid} is timeout')
                await job_return_service.update(
                    query={'jid': job.jid, 'status': JobReturnStatus.waiting},
                    data={'status': JobReturnStatus.timeout},
                    projection_model=EmptyModel,
                )
                await job_service.update(query=job.id, data={'status': JobStatus.finished})

            await asyncio.sleep(1)


async def async_main() -> None:
    logger.info('Starting jobs watcher')
    watcher = JobsWatcher()
    await watcher.process()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
