import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from faststream import ContextRepo

from saltbox_core.event_bus.rabbit.routers.scheduler import router as scheduler_router
from saltbox_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.minion_collections.repositories.collection_repository import (
    CollectionRepository,
    get_collection_repository,
)
from saltbox_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.pillars.services.pillar_service import PillarService, get_pillar_service
from saltbox_core.tasks.repositories.task_repository import TaskRepository, get_task_repository
from saltbox_core.tasks.repositories.task_template_repository import (
    TaskTemplateRepository,
    get_task_template_repository,
)
from saltbox_core.tasks.services.tasks import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service
from saltbox_sdk.config.logger_config import logger
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.redis.config import get_redis_now
from saltbox_sdk.event_bus.faststream_app import get_faststream_app


@asynccontextmanager
async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
    mongo_db = get_mongo_db()
    redis_db = get_redis_now()

    master_repository: MasterRepository = get_master_repository(db=mongo_db)
    master_service: MasterService = get_master_service(repo=master_repository)
    collection_repository: CollectionRepository = get_collection_repository(db=mongo_db)
    collection_service: CollectionService = get_collection_service(repo=collection_repository)
    minion_repository: MinionRepository = get_minion_repository(db=mongo_db)
    minion_service: MinionService = get_minion_service(repo=minion_repository)
    job_schema_repository: JobSchemaRepository = get_job_schema_repository(db=mongo_db)
    job_schema_service: JobSchemaService = get_job_schema_service(repo=job_schema_repository)
    job_repository: JobRepository = get_job_repository(db=redis_db)
    job_service: JobService = await get_job_service(
        rdb=redis_db,
        job_repository=job_repository,
        job_schema_service=job_schema_service,
        master_service=master_service,
    )
    task_template_repository: TaskTemplateRepository = get_task_template_repository(db=mongo_db)
    task_template_service: TaskTemplateService = await get_task_template_service(repo=task_template_repository)
    task_repository: TaskRepository = get_task_repository(db=mongo_db)
    task_service: TaskService = await get_task_service(
        repo=task_repository,
        rdb=redis_db,
        task_template_service=task_template_service,
        job_schema_service=job_schema_service,
        collections_service=collection_service,
    )
    pillar_service: PillarService = get_pillar_service(
        redis_client=redis_db, minion_service=minion_service, master_service=master_service
    )

    context.set_global('master_service', master_service)
    context.set_global('collection_service', collection_service)
    context.set_global('minion_service', minion_service)
    context.set_global('job_schema_service', job_schema_service)
    context.set_global('job_service', job_service)
    context.set_global('task_template_service', task_template_service)
    context.set_global('task_service', task_service)
    context.set_global('pillar_service', pillar_service)

    yield

    del pillar_service
    del task_service
    del task_repository
    del task_template_service
    del task_template_repository
    del job_service
    del job_repository
    del job_schema_service
    del job_schema_repository
    del minion_service
    del minion_repository
    del collection_service
    del collection_repository
    del master_service
    del master_repository


async def async_main() -> None:
    app = get_faststream_app(lifespan=lifespan, routers=[scheduler_router])
    logger.info('Starting faststream app')
    await app.run()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
