from typing import Annotated

from fastapi import Depends

from saltbox_core.minion_collections.repositories.extra_data_category import (
    ExtraDataCategoryRepository,
    get_extra_data_category_repository,
)
from saltbox_core.minion_collections.schemas.extra_data_category import (
    ExtraDataCategoryCreateSchema,
    ExtraDataCategoryModel,
    ExtraDataCategoryUpdateSchema,
)
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class ExtraDataCategoryService(
    MongoBaseService[
        ExtraDataCategoryRepository,
        ExtraDataCategoryModel,
        ExtraDataCategoryCreateSchema,
        ExtraDataCategoryUpdateSchema,
    ]
): ...


def get_extra_data_category_service(
    repo: Annotated[ExtraDataCategoryRepository, Depends(get_extra_data_category_repository)],
) -> ExtraDataCategoryService:
    return ExtraDataCategoryService(repo)
