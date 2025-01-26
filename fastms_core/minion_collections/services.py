from fastapi import HTTPException

from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minion_collections.repository import CollectionRepository, MinionRepository
from fastms_core.minion_collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionDetailSchema,
    MinionCollectionListSchema,
    MinionCollectionSchema,
)


class MinionCollectionService:
    def __init__(self) -> None:
        self.collections_repo = CollectionRepository()
        self.minions_repo = MinionRepository()

    async def get_list(
        self, query: dict | None = None, *, page: int = 0, per_page: int = 20
    ) -> PaginatedResponse[MinionCollectionListSchema]:
        response = await self.collections_repo.get_paginated(query, page=page, per_page=per_page)

        return PaginatedResponse[MinionCollectionListSchema](**response)

    async def get_by_slug(self, slug: str, *, page: int = 0, per_page: int = 20) -> MinionCollectionDetailSchema:
        collection = await self.collections_repo.find_one({'slug': slug})
        if not collection:
            raise HTTPException(status_code=404, detail='Collection not found')

        projection_query = {
            'minion_id': 1,
            'master': 1,
            'grains.id': 1,
            'grains.fqdn': 1,
            'grains.osfullname': 1,
            'grains.domain': 1,
            'grains.efi': 1,
            'grains.cpu_model': 1,
            'grains.mem_total': 1,
            'created': 1,
            'modified': 1,
        }

        minions = await self.minions_repo.get_paginated(
            collection.query, page=page, per_page=per_page, projection_query=projection_query
        )

        return MinionCollectionDetailSchema(
            **collection.model_dump(),
            minions={**minions},
        )

    async def create(self, data: MinionCollectionCreateSchema) -> MinionCollectionSchema:
        if data.slug == 'default':
            raise HTTPException(status_code=400, detail='Slug `default` is reserved')
        collection = await self.collections_repo.add(data)
        if not collection:
            raise HTTPException(status_code=400, detail='Collection not created')

        return collection


def get_collection_service() -> MinionCollectionService:
    return MinionCollectionService()
