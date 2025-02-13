from typing import Annotated, Any

from fastapi import Depends
from pymongo.errors import OperationFailure

from salt_box_core.db.exceptions import PiplineBuilderError
from salt_box_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from salt_box_core.minion_collections.schemas.minion_schemas import (
    MinionCreateSchema,
    MinionIDs,
    MinionModel,
    MinionShortSchema,
    MinionUpdateSchema,
)
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class MinionService(MongoBaseService[MinionRepository, MinionModel, MinionCreateSchema, MinionUpdateSchema]):


    async def get_ids_by_query(self, query: dict[str, Any]) -> list[MinionIDs]:
        return await self.repo.get_list(query, skip=0, limit=0, projection_model=MinionIDs)

    async def minion_pipeline(self, pipeline: list[dict]) -> list:
        try:
            cursor = await self.repo.collection.aggregate(pipeline)
            return await cursor.to_list()
        except OperationFailure as e:
            msg = f'Error during pipeline execution: {e}'
            raise PiplineBuilderError(msg) from e


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)
