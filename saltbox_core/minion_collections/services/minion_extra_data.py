from typing import Annotated, Any

from fastapi import Depends

from saltbox_core.minion_collections.repositories.minion_extra_data import (
    MinionExtraDataItemRepository,
    get_minion_extra_data_item_repository,
)
from saltbox_core.minion_collections.schemas.minion_extra_data import (
    MinionExtraDataItemCreateSchema,
    MinionExtraDataItemModel,
    MinionExtraDataItemUpdateSchema,
)
from saltbox_sdk.exceptions import DuplicateKeyException, ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel


class MinionExtraDataItemService(
    MongoBaseService[
        MinionExtraDataItemRepository,
        MinionExtraDataItemModel,
        MinionExtraDataItemCreateSchema,
        MinionExtraDataItemUpdateSchema,
    ]
):
    async def get_or_create(
        self, source: str, name: str, value: Any, projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | MinionExtraDataItemModel:
        query = {'source': source, 'name': name, 'value': value}

        try:
            if projection_model:
                return await self.get(query=query, projection_model=projection_model)
            else:
                return await self.get(query=query)
        except ObjectNotFoundException:
            try:
                await self.create(data=MinionExtraDataItemCreateSchema(**query))
            except DuplicateKeyException:
                ...

        if projection_model:
            return await self.get(query=query, projection_model=projection_model)
        else:
            return await self.get(query=query)


def get_minion_extra_data_item_service(
    repo: Annotated[MinionExtraDataItemRepository, Depends(get_minion_extra_data_item_repository)],
) -> MinionExtraDataItemService:
    return MinionExtraDataItemService(repo)
