from typing import Annotated, ClassVar

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import BaseMongoRepository
from salt_box_core.masters.schemas.master_schemas import MasterModel


class MasterRepository(BaseMongoRepository[MasterModel]):
    class Meta:
        collection_name = 'master'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']


def get_master_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> MasterRepository:
    return MasterRepository(db)
