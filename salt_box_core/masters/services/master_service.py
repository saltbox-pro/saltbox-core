from typing import Annotated, Any

from fastapi import Depends

from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from salt_box_core.masters.schemas.master_schemas import (
    MasterCreateSchema,
    MasterModel,
    MasterStatus,
    MasterUpdateSchema,
)
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class MasterService(MongoBaseService[MasterRepository, MasterModel, MasterCreateSchema, MasterUpdateSchema]):
    async def get_by_name(self, name: str) -> MasterModel:
        return await self.repo.get({'name': name})

    async def get_by_alias(self, name: str) -> MasterModel:
        return await self.repo.get({'alias': name})

    async def get_by_name_or_alias(self, value: str) -> MasterModel:
        return await self.repo.get({'$or': [{'name': value}, {'alias': value}]})

    async def accept(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.accepted})

    async def reject(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.rejected})

    async def get_master_key(self, value: str) -> str:
        master = await self.get_by_name_or_alias(value)

        return master.alias if master.alias else master.name


def get_master_service(repo: Annotated[MasterRepository, Depends(get_master_repository)]) -> MasterService:
    return MasterService(repo)
