from __future__ import annotations

import logging.config

from pymongo import AsyncMongoClient

from fastms_core.config import LOG_CONFIG, SETTINGS

logger = logging.getLogger(__name__)
logging.config.dictConfig(LOG_CONFIG.model_dump())


class _MongoClientSingleton:
    mongo_client: AsyncMongoClient | None

    def __new__(cls) -> _MongoClientSingleton:
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.mongo_client = AsyncMongoClient(SETTINGS.mongo_url)
        return cls.instance


async def init_mongo() -> AsyncMongoClient:
    client = _MongoClientSingleton().mongo_client

    if client is None:
        msg = 'Mongo client is not initialized'
        raise ValueError(msg)

    # mongo_db = client[SETTINGS.mongo_db]

    return client
