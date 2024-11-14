from __future__ import annotations

import logging.config

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.minions.models import Minion

logger = logging.getLogger(__name__)
logging.config.dictConfig(LOG_CONFIG.model_dump())


class _MongoClientSingleton:
    mongo_client: AsyncIOMotorClient | None

    def __new__(cls) -> _MongoClientSingleton:
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
            cls.instance.mongo_client = AsyncIOMotorClient(SETTINGS.mongo_url)
        return cls.instance


async def init_mongo() -> AsyncIOMotorClient:
    client = _MongoClientSingleton().mongo_client

    if client is None:
        msg = 'Mongo client is not initialized'
        raise ValueError(msg)

    mongo_db = client[SETTINGS.mongo_db]
    await init_beanie(mongo_db, document_models=[Minion])

    return client
