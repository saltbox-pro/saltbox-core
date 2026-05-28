from typing import Annotated, Any

from fastapi import Depends

from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository, get_extra_data_repository
from saltbox_core.minion_collections.schemas.extra_data import (
    ExtraDataCreateSchema,
    ExtraDataModel,
    ExtraDataUpdateSchema,
)
from saltbox_sdk.exceptions import DuplicateKeyException, ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel


class ExtraDataService(
    MongoBaseService[
        ExtraDataRepository,
        ExtraDataModel,
        ExtraDataCreateSchema,
        ExtraDataUpdateSchema,
    ]
):
    async def get_or_create(
        self, source: str, name: str, value: Any, projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | ExtraDataModel:
        query = {'source': source, 'name': name, 'value': value}

        try:
            if projection_model:
                return await self.get(query=query, projection_model=projection_model)
            else:
                return await self.get(query=query)
        except ObjectNotFoundException:
            try:
                await self.create(data=ExtraDataCreateSchema(**query))
            except DuplicateKeyException:
                ...

        if projection_model:
            return await self.get(query=query, projection_model=projection_model)
        else:
            return await self.get(query=query)


def get_extra_data_service(
    repo: Annotated[ExtraDataRepository, Depends(get_extra_data_repository)],
) -> ExtraDataService:
    return ExtraDataService(repo)
