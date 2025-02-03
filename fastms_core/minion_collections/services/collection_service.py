from typing import Annotated, Any

from fastapi import Depends

from fastms_core.db.exceptions import ObjectNotFoundError
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.minion_collections.repositories.collection_repository import (
    CollectionRepository,
    get_collection_repository,
)
from fastms_core.minion_collections.schemas.collection_schemas import (
    CollectionCreateSchema,
    CollectionModel,
    CollectionUpdateSchema,
)


class CollectionService:
    def __init__(self, repo: CollectionRepository):
        self.repo = repo

    async def get_by_slug(self, slug: str) -> CollectionModel:
        document = await self.repo.find_one({'slug': slug})
        if not document:
            msg = 'Collection not found'
            raise ObjectNotFoundError(msg)
        return document

    async def get_by_slug_or_none(self, slug: str) -> CollectionModel | None:
        return await self.repo.find_one({'slug': slug})

    async def create(self, document: CollectionCreateSchema) -> CollectionModel:
        return await self.repo.create(document)

    async def get_paginated(
        self, query: dict[str, Any] | None = None, limit: int = 0, skip: int = 0
    ) -> PaginatedResponse[CollectionModel]:
        total = await self.repo.count(query)
        docs = await self.repo.find_all(query, limit=limit, skip=skip)
        return PaginatedResponse[CollectionModel](total=total, data=docs)

    async def update(self, slug: str, document: CollectionUpdateSchema) -> CollectionModel:
        result = await self.repo.update({'slug': slug}, document)
        return result


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> CollectionService:
    return CollectionService(repo)
