from typing import Annotated, TypeVar, overload, override
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel

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

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class CollectionService(
    MongoBaseService[CollectionRepository, CollectionModel, CollectionCreateSchema, CollectionUpdateSchema]
):
    async def get_by_slug(self, slug: str) -> CollectionModel:
        return await self.repo.get(query={'slug': slug})

    async def get_by_slug_or_none(self, slug: str) -> CollectionModel | None:
        return await self.repo.get(query={'slug': slug})

    async def update_by_slug(self, slug: str, data: CollectionUpdateSchema) -> CollectionModel:
        result = await self.update(query={'slug': slug}, data=data)
        return result

    async def delete_by_slug(self, slug: str) -> int:
        result = await self.delete(query={'slug': slug})
        return result

    @overload
    async def create(self, data: CollectionCreateSchema) -> CollectionModel: ...

    @overload
    async def create(
        self, data: CollectionCreateSchema, *, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    @override
    async def create(
        self, data: CollectionCreateSchema, *, projection_model: type[ProjectionModel] | None = None
    ) -> CollectionModel | ProjectionModel:
        while True:
            existing = await self.exists({'slug': data.slug})
            if not existing:
                break
            data.slug = f'{data.slug.split("-")[0]}-{uuid4().hex[:8]}'
        if projection_model:
            return await super().create(data=data, projection_model=projection_model)
        return await super().create(data=data)


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> CollectionService:
    return CollectionService(repo)


CollectionServiceDependency = Annotated[CollectionService, Depends(get_collection_service)]
