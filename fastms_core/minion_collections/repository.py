from fastapi import HTTPException

from fastms_core.db.mongo.repository_base import MongoDBRepository
from fastms_core.minion_collections.schemas.collection_schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListSchema,
    MinionCollectionSchema,
    MinionCollectionUpdateSchema,
)
from fastms_core.minion_collections.schemas.minion_schemas import (
    MinionCreateSchema,
    MinionListSchema,
    MinionSchema,
    MinionUpdateSchema,
)


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
