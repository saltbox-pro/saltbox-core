from typing import Annotated, Any

from fastapi import Depends

from saltbox_bridge_messages import MasterStatus
from saltbox_core.masters.repositories.master_repository import MasterRepository, get_master_repository
from saltbox_core.masters.schemas.master_schemas import (
    MasterCreateSchema,
    MasterModel,
    MasterUpdateSchema,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class MasterService(MongoBaseService[MasterRepository, MasterModel, MasterCreateSchema, MasterUpdateSchema]):
    async def get_by_master_id(self, master_id: str) -> MasterModel:
        return await self.repo.get({'master_id': master_id})

    async def get_accepted_by_master_id(self, master_id: str) -> MasterModel:
        return await self.repo.get({'status': MasterStatus.ACCEPTED, 'master_id': master_id})

    async def accept(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.ACCEPTED})

    async def reject(self, query: dict[str, Any] | PyObjectId) -> MasterModel:
        return await self.update(query=query, data={'status': MasterStatus.REJECTED})

    async def get_accepted_list(self) -> list[MasterModel]:
        return await self.get_list(query={'status': 'accepted'}, skip=0, limit=0)


def get_master_service(repo: Annotated[MasterRepository, Depends(get_master_repository)]) -> MasterService:
    return MasterService(repo)
