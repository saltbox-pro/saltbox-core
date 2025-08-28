from typing import Annotated

from fastapi import Depends

from saltbox_core.minion_collections.repositories.collection_repository import (
    CollectionRepository,
    get_collection_repository,
)
from saltbox_core.minion_collections.schemas.collection_schemas import (
    CollectionCreateSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class CollectionService(
    MongoBaseService[CollectionRepository, CollectionModel, CollectionCreateSchema, CollectionUpdateSchema]
):
    async def get_by_slug(self, slug: str) -> CollectionModel:
        return await self.repo.get({'slug': slug})

    async def get_by_slug_or_none(self, slug: str) -> CollectionModel | None:
        return await self.repo.get({'slug': slug})

    async def update_by_slug(self, slug: str, data: CollectionUpdateSchema) -> CollectionModel:
        result = await self.update({'slug': slug}, data)
        return result

    async def delete_by_slug(self, slug: str) -> int:
        result = await self.delete({'slug': slug})
        return result


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> CollectionService:
    return CollectionService(repo)


CollectionServiceDependency = Annotated[CollectionService, Depends(get_collection_service)]
