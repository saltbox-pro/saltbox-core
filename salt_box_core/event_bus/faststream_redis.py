import asyncio
import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from faststream import ContextRepo, FastStream
from faststream.redis import RedisBroker
from faststream.redis.publisher.asyncapi import AsyncAPIPublisher
from faststream.redis.subscriber.asyncapi import AsyncAPISubscriber
from faststream.security import SASLPlaintext

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.event_bus.masters_subscribers import router as masters_router
from salt_box_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service


def get_faststream_broker() -> RedisBroker:
    if SETTINGS.redis_username is None or SETTINGS.redis_password is None:
        msg = 'You must provide both `redis_username` and `redis_password`'
        raise ValueError(msg)

    if SETTINGS.redis_url.startswith('rediss:'):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ssl_context.verify_mode = {
            'none': ssl.CERT_NONE,
            'required': ssl.CERT_REQUIRED,
            'optional': ssl.CERT_OPTIONAL,
        }[SETTINGS.redis_tls_verification]

        if SETTINGS.redis_ca_cert:
            ssl_context.load_verify_locations(cafile=os.path.relpath(SETTINGS.redis_ca_cert), capath=None, cadata=None)

        security = SASLPlaintext(
            username=SETTINGS.redis_username, password=SETTINGS.redis_password, ssl_context=ssl_context
        )
    else:
        security = SASLPlaintext(username=SETTINGS.redis_username, password=SETTINGS.redis_password)

    return RedisBroker(url=SETTINGS.redis_url, security=security)


def get_faststream_subscriber(channel: str) -> AsyncAPISubscriber:
    broker: RedisBroker = get_faststream_broker()

    return broker.subscriber(channel)


def get_faststream_publisher(channel: str) -> AsyncAPIPublisher:
    broker: RedisBroker = get_faststream_broker()

    return broker.publisher(channel)


@asynccontextmanager
async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
    mongo_db = get_mongo_db()
    minion_repository: MinionRepository = get_minion_repository(db=mongo_db)
    minion_service: MinionService = get_minion_service(minion_repository)

    context.set_global('minion_service', minion_service)

    yield

    del minion_service
    del minion_repository


def get_faststream_app() -> FastStream:
    broker: RedisBroker = get_faststream_broker()

    # Include your FastStream routers here
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
