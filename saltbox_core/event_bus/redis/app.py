import asyncio
import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from faststream import ContextRepo, FastStream
from faststream.broker.types import BrokerMiddleware
from faststream.redis import RedisBroker
from faststream.security import SASLPlaintext
from redis import asyncio as aioredis

from saltbox_core.config import logger
from saltbox_core.event_bus.redis.masters_subscribers import router as masters_router
from saltbox_core.event_bus.redis.masters_subscribers import router_not_auth as masters_router_not_auth
from saltbox_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_sdk.config.redis_config import REDIS_SETTINGS
from saltbox_sdk.db.mongo.config import get_mongo_db


def get_faststream_broker(middlewares: list[BrokerMiddleware] | None = None) -> RedisBroker:
    if REDIS_SETTINGS.redis_username is None or REDIS_SETTINGS.redis_password is None:
        msg = 'You must provide both `redis_username` and `redis_password`'
        raise ValueError(msg)

    if REDIS_SETTINGS.redis_url.startswith('rediss:'):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ssl_context.verify_mode = {
            'none': ssl.CERT_NONE,
            'required': ssl.CERT_REQUIRED,
            'optional': ssl.CERT_OPTIONAL,
        }[REDIS_SETTINGS.redis_tls_verification]

        if REDIS_SETTINGS.redis_ca_cert:
            ssl_context.load_verify_locations(
                cafile=os.path.relpath(REDIS_SETTINGS.redis_ca_cert), capath=None, cadata=None
            )

        security = SASLPlaintext(
            username=REDIS_SETTINGS.redis_username, password=REDIS_SETTINGS.redis_password, ssl_context=ssl_context
        )
    else:
        security = SASLPlaintext(username=REDIS_SETTINGS.redis_username, password=REDIS_SETTINGS.redis_password)

    if middlewares:
        return RedisBroker(url=REDIS_SETTINGS.redis_url, security=security, middlewares=middlewares)

    return RedisBroker(url=REDIS_SETTINGS.redis_url, security=security)


@asynccontextmanager
async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
    mongo_db = get_mongo_db()
    redis_db = await aioredis.from_url(REDIS_SETTINGS.redis_url, **REDIS_SETTINGS.redis_connection_kwargs)
    master_repository: MasterRepository = get_master_repository(db=mongo_db)
    master_service: MasterService = get_master_service(repo=master_repository)
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

    context.set_global('master_service', master_service)
    context.set_global('minion_service', minion_service)
    context.set_global('job_schema_repository', job_schema_repository)
    context.set_global('job_service', job_service)

    yield


def get_faststream_app() -> FastStream:
    # broker: RedisBroker = get_faststream_broker(middlewares=[MastersAuthMiddleware])
    broker: RedisBroker = get_faststream_broker()

    # Include your FastStream routers here
    broker.include_router(masters_router_not_auth)
    broker.include_router(masters_router)

    return FastStream(broker, lifespan=lifespan)


async def async_main() -> None:
    app: FastStream = get_faststream_app()
    logger.info('Starting faststream app')
    await app.run()


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
