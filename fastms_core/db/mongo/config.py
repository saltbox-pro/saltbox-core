from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from fastms_core.config import SETTINGS


class _MongoClientSingleton:
    mongo_client: AsyncMongoClient | None

    def __new__(cls) -> '_MongoClientSingleton':
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.mongo_client = AsyncMongoClient(SETTINGS.mongo_url)
        return cls.instance


def get_mongo_db() -> AsyncDatabase:
    client = _MongoClientSingleton().mongo_client

    if client is None:
        msg = 'Mongo client is not initialized'
        raise ValueError(msg)

    mongo_db = client[SETTINGS.mongo_db]

    return mongo_db
