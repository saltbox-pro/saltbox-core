import logging.config

from fastapi import HTTPException

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.repository_base import MongoDBRepository
from fastms_core.minion_collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListSchema,
    MinionCollectionSchema,
    MinionCollectionUpdateSchema,
    MinionCreateSchema,
    MinionListSchema,
    MinionSchema,
    MinionUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CollectionRepository(
    MongoDBRepository[
        MinionCollectionSchema, MinionCollectionListSchema, MinionCollectionCreateSchema, MinionCollectionUpdateSchema
    ]
):
    def __init__(self) -> None:
        super().__init__('minion_collections', MinionCollectionSchema)

    async def add(self, document: MinionCollectionCreateSchema) -> MinionCollectionSchema | None:
        exist = await self.collection.find_one({'slug': document.slug})
        if exist:
            raise HTTPException(status_code=400, detail='Collection with this slug already exists')

        return await super().add(document)


class MinionRepository(MongoDBRepository[MinionSchema, MinionListSchema, MinionCreateSchema, MinionUpdateSchema]):
    def __init__(self) -> None:
        super().__init__('minions', MinionSchema)
