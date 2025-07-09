from typing import Annotated, Any

from fastapi import Depends

from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from salt_box_core.masters.schemas.master_schemas import (
    MasterCreateSchema,
    MasterModel,
    MasterUpdateSchema,
)
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService
from saltbox_bridge_messages import MasterStatus


class MasterService(MongoBaseService[MasterRepository, MasterModel, MasterCreateSchema, MasterUpdateSchema]):
    async def get_by_master_id(self, master_id: str) -> MasterModel:
        return await self.repo.get({'master_id': master_id})

    async def accept(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.ACCEPTED})

    async def reject(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.REJECTED})

    async def get_accepted_list(self) -> list[MasterModel]:
        return await self.get_list(query={'status': 'accepted'}, skip=0, limit=0)


def get_master_service(repo: Annotated[MasterRepository, Depends(get_master_repository)]) -> MasterService:
    return MasterService(repo)
