import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from faststream import ContextRepo

from saltbox_core.event_bus.rabbit.exchanges import exchanges
from saltbox_core.event_bus.rabbit.routers.jobs import router as job_router
from saltbox_core.event_bus.rabbit.routers.minions import router as minion_router
from saltbox_core.event_bus.rabbit.routers.scheduler import router as scheduler_router
from saltbox_core.jobs.repositories.job_repository import get_job_repository
from saltbox_core.jobs.repositories.job_return_repository import get_job_return_repository
from saltbox_core.jobs.repositories.job_sc_repository import get_job_schema_repository
from saltbox_core.jobs.services.job_return_service import get_job_return_service
from saltbox_core.jobs.services.job_sc_service import get_job_schema_service
from saltbox_core.jobs.services.job_services import get_job_service
from saltbox_core.masters.repositories.master_repository import get_master_repository
from saltbox_core.masters.services.master_service import get_master_service
from saltbox_core.minion_collections.repositories.collection import get_collection_repository
from saltbox_core.minion_collections.repositories.minion import get_minion_repository
from saltbox_core.minion_collections.repositories.minion_extra_data import get_minion_extra_data_item_repository
from saltbox_core.minion_collections.services.collection import get_collection_service
from saltbox_core.minion_collections.services.minion import get_minion_service
from saltbox_core.minion_collections.services.minion_extra_data import get_minion_extra_data_item_service
from saltbox_core.tasks.repositories.task import get_task_repository
from saltbox_core.tasks.repositories.tasks_minion import get_task_minion_repository
from saltbox_core.tasks.repositories.tasks_status import get_task_status_repository
from saltbox_core.tasks.repositories.tasks_template import get_task_template_repository
from saltbox_core.tasks.services.task import get_task_service
from saltbox_core.tasks.services.tasks_minion import get_task_minion_service
from saltbox_core.tasks.services.tasks_status import get_task_status_service
from saltbox_core.tasks.services.tasks_template import get_task_template_service
from saltbox_core.tkq import shutdown_broker, startup_broker
from saltbox_sdk.config.logger_config import logger
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.redis.config import get_redis_now
from saltbox_sdk.event_bus.faststream_app import get_faststream_app, get_faststream_broker


@asynccontextmanager
async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
    mongo_db = get_mongo_db()
    redis_db = get_redis_now()

    master_repository = get_master_repository(db=mongo_db)
    master_service = get_master_service(repo=master_repository)
    collection_repository = get_collection_repository(db=mongo_db)
    collection_service = get_collection_service(repo=collection_repository)
    minion_extra_data_item_repository = get_minion_extra_data_item_repository(db=mongo_db)
    minion_extra_data_item_service = get_minion_extra_data_item_service(repo=minion_extra_data_item_repository)
    minion_repository = get_minion_repository(db=mongo_db)
    minion_service = get_minion_service(repo=minion_repository)
    job_schema_repository = get_job_schema_repository(db=mongo_db)
    job_schema_service = get_job_schema_service(repo=job_schema_repository)
    job_repository = get_job_repository(db=mongo_db)
    job_return_repository = get_job_return_repository(db=mongo_db, rdb=redis_db)
    job_return_service = get_job_return_service(rdb=redis_db, repo=job_return_repository)
    job_service = get_job_service(
        rdb=redis_db,
        job_repository=job_repository,
        job_schema_service=job_schema_service,
        job_return_service=job_return_service,
        master_service=master_service,
    )
    task_template_repository = get_task_template_repository(db=mongo_db)
    task_template_service = get_task_template_service(repo=task_template_repository)
    task_minion_repository = get_task_minion_repository(db=mongo_db)
    task_minion_service = get_task_minion_service(repo=task_minion_repository, rdb=redis_db)
    task_status_repository = get_task_status_repository(db=mongo_db)
    task_status_service = get_task_status_service(repo=task_status_repository)
    task_repository = get_task_repository(db=mongo_db)
    task_service = get_task_service(
        repo=task_repository,
        rdb=redis_db,
        task_status_service=task_status_service,
        task_template_service=task_template_service,
        task_minion_service=task_minion_service,
        job_schema_service=job_schema_service,
        collections_service=collection_service,
        minion_service=minion_service,
    )

    context.set_global('service_name', 'core')
    context.set_global('redis_db', redis_db)
    context.set_global('mongo_db', mongo_db)
    context.set_global('master_service', master_service)
    context.set_global('collection_service', collection_service)
    context.set_global('minion_extra_data_item_service', minion_extra_data_item_service)
    context.set_global('minion_service', minion_service)
    context.set_global('job_schema_service', job_schema_service)
    context.set_global('job_service', job_service)
    context.set_global('job_return_service', job_return_service)
    context.set_global('task_template_service', task_template_service)
    context.set_global('task_minion_service', task_minion_service)
    context.set_global('task_service', task_service)

    try:
        yield
    finally:
        del task_service
        del task_repository
        del task_minion_service
        del task_minion_repository
        del task_template_service
        del task_template_repository
        del job_return_service
        del job_return_repository
        del job_service
        del job_repository
        del job_schema_service
        del job_schema_repository
        del minion_service
        del minion_extra_data_item_service
        del minion_repository
        del collection_service
        del collection_repository
        del master_service
        del master_repository


async def async_main() -> None:
    broker = get_faststream_broker()
    app = get_faststream_app(broker=broker, lifespan=lifespan, routers=[job_router, scheduler_router, minion_router])

    @app.after_startup
    async def declare_exchanges() -> None:
        for exchange in exchanges.values():
            await broker.declare_exchange(exchange)

    await startup_broker()
    logger.info('Starting faststream app')
    await app.run()
    await shutdown_broker()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
