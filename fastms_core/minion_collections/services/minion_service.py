from typing import Annotated, Any

from fastapi import Depends

from fastms_core.db.exceptions import ObjectNotFoundError
from fastms_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from fastms_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from fastms_core.minion_collections.schemas.minion_schemas import (
    MinionCreateSchema,
    MinionIDs,
    MinionModel,
    MinionShortSchema,
    MinionUpdateSchema,
)


class MinionService:
    def __init__(self, repo: MinionRepository):
        self.repo = repo

    async def get(self, id: PyObjectId) -> MinionModel:
        document = await self.repo.find_one({'_id': id})
        if not document:
            msg = 'Minion not found'
            raise ObjectNotFoundError(msg)
        return document

    async def get_or_none(self, id: PyObjectId) -> MinionModel | None:
        return await self.repo.find_one({'_id': id})

    async def create(self, document: MinionCreateSchema) -> MinionModel:
        return await self.repo.create(document)

    async def get_paginated(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
    ) -> PaginatedResponse[MinionShortSchema]:
        total = await self.repo.count(query)
        docs = await self.repo.find_all(
            query,
            limit=limit,
            skip=skip,
            projection_model=MinionShortSchema,
        )
        # logger.info('docs: %s', docs)
        return PaginatedResponse[MinionShortSchema](total=total, data=docs)

    async def update(self, id: str, document: MinionUpdateSchema) -> MinionModel:
        result = await self.repo.update({'_id': id}, document)
        return result

    async def get_ids_by_query(self, query: dict[str, Any]) -> list[MinionIDs]:
        return await self.repo.find_all(query, skip=0, limit=0, projection_model=MinionIDs)

    async def minion_pipeline(self, pipeline: list[dict]) -> list:
        cursor = await self.repo.collection.aggregate(pipeline)
        return await cursor.to_list()


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)
