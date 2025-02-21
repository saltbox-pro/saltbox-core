from typing import Annotated, TypeVar

from fastapi import Depends
from pydantic import BaseModel

# from salt_box_core.config import logger
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.sls_repos.repository import SlsTplRepository, get_sls_tpl_repository
from salt_box_core.sls_repos.schemas.tpl_schemas import (
    SlsTplCreateSchema,
    SlsTplModel,
    SlsTplUpdateSchema,
)
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class SlsTplService(MongoBaseService[SlsTplRepository, SlsTplModel, SlsTplCreateSchema, SlsTplUpdateSchema]):
    async def get_by_name(self, name: str, sid: PyObjectId) -> SlsTplModel:
        return await self.repo.get({'name': name, 'repo_id': sid})


def get_sls_tpl_service(
    repo: Annotated[SlsTplRepository, Depends(get_sls_tpl_repository)],
) -> SlsTplService:
    return SlsTplService(repo)
