from typing import Generator

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.config import SETTINGS, logger


class _MongoClientSingleton:
    mongo_client: AsyncMongoClient | None

    def __new__(cls) -> '_MongoClientSingleton':
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.mongo_client = AsyncMongoClient(SETTINGS.mongo_url)
            logger.debug('Mongo initialized')
        return cls.instance


def get_mongo_db(db_name: str = SETTINGS.mongo_db) -> AsyncDatabase:
    client = _MongoClientSingleton().mongo_client

    if client is None:
        msg = 'Mongo client is not initialized'
        raise ValueError(msg)

    mongo_db = client[db_name]

    return mongo_db


# TODO (a.baikov): Shuld we use generator
def get_mongo() -> Generator[AsyncDatabase, None, None]:
    try:
        db = get_mongo_db()
        yield db
    finally:
        pass
