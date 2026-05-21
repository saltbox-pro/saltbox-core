from typing import Annotated, Any

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

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
    async def get_by_master_id(
        self,
        master_id: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> MasterModel:
        return await self.repo.get(query={'master_id': master_id}, session=session)

    async def get_accepted_by_master_id(
        self,
        master_id: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> MasterModel:
        return await self.repo.get(query={'status': MasterStatus.ACCEPTED, 'master_id': master_id}, session=session)

    async def accept(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> MasterModel:
        obj_id = await self.update(query=query, data={'status': MasterStatus.ACCEPTED}, session=session)

        return await self.get(query=obj_id, session=session)

    async def reject(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> MasterModel:
        obj_id = await self.update(query=query, data={'status': MasterStatus.REJECTED}, session=session)

        return await self.get(query=obj_id, session=session)

    async def get_accepted_list(
        self,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> list[MasterModel]:
        return await self.get_list(query={'status': 'accepted'}, skip=0, limit=0, session=session)


def get_master_service(repo: Annotated[MasterRepository, Depends(get_master_repository)]) -> MasterService:
    return MasterService(repo)
