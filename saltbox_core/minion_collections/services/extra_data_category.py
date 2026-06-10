from typing import Annotated, Any

from fastapi import Depends

from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class ExtraDataCategoryService(
    MongoBaseService[
        ExtraDataCategoryRepository,
        ExtraDataCategoryModel,
        ExtraDataCategoryCreateSchema,
        ExtraDataCategoryUpdateSchema,
    ]
):
    async def process_data(self, *, minion_id: PyObjectId, collector_id: PyObjectId, data: Any) -> None:
        categories = await self.get_list(query={'collector_id': collector_id})

        for category in categories:
            logger.warning('Processing data for %s', category)


def get_extra_data_category_service(
    repo: Annotated[ExtraDataCategoryRepository, Depends(get_extra_data_category_repository)],
) -> ExtraDataCategoryService:
    return ExtraDataCategoryService(repo)
