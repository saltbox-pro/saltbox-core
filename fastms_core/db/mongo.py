import logging
from collections.abc import Generator

from motor import core, motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine
from pymongo.driver_info import DriverInfo

from fastms_core.config import LOG_CONFIG, SETTINGS

DRIVER_INFO = DriverInfo(name='fastms')

LOGGER = logging.getLogger(__name__)
logging.config.dictConfig(LOG_CONFIG.model_dump())


class _MongoClientSingleton:
    mongo_client: motor_asyncio.AsyncIOMotorClient | None
    engine: AIOEngine

    def __new__(cls) -> '_MongoClientSingleton':
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.mongo_client = AsyncIOMotorClient(SETTINGS.mongo_url, driver=DRIVER_INFO)
            cls.instance.engine = AIOEngine(client=cls.instance.mongo_client, database=SETTINGS.mongo_db)
        return cls.instance


def mongo_db() -> core.AgnosticDatabase:
    client = _MongoClientSingleton().mongo_client
    if client is None:
        msg = 'Mongo client is not initialized'
        raise ValueError(msg)
    return client[SETTINGS.mongo_db]


def get_engine() -> AIOEngine:
    return _MongoClientSingleton().engine


async def ping() -> None:
    await mongo_db().command('ping')


def get_db() -> Generator:
    try:
        db = mongo_db()
        yield db
    finally:
        pass


# __all__ = ['mongo_db', 'ping']
