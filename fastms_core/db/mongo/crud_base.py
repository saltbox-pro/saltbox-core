import logging.config
from datetime import datetime
from typing import Any, Generic, TypeVar

from beanie import Document, PydanticObjectId
from beanie.odm.queries.find import FindMany
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

ModelType = TypeVar('ModelType', bound=Document)
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)
ListSchemaType = TypeVar('ListSchemaType', bound=BaseModel)
FindQueryProjectionType = TypeVar('FindQueryProjectionType', bound=BaseModel)


class CRUDBase(Generic[ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, id: PydanticObjectId) -> ModelType | None:
        return await self.model.get(id)

    async def get_multi(
        self, search: dict, *, projection_model: type[FindQueryProjectionType] | None = None
    ) -> list[ListSchemaType]:
        if projection_model:
            data_query: FindMany[Any] = self.model.find(search).project(projection_model)
        else:
            data_query = self.model.find(search)
        data = await data_query.to_list()

        return data

    async def get_paginated(
        self,
        search: dict,
        *,
        page: int = 0,
        per_page: int = 20,
        projection_model: type[FindQueryProjectionType] | None = None,
    ) -> PaginatedResponse[ListSchemaType]:
        data_query = self.model.find(search).project(projection_model).limit(per_page).skip(page * per_page)
        data = await data_query.to_list()
        total = await data_query.count()

        return PaginatedResponse[ListSchemaType](total=total, data=data)

    async def create(self, *, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data)
        return await db_obj.insert()

    async def update(self, *, db_obj: ModelType, obj_in: UpdateSchemaType | dict[str, Any]) -> ModelType:
        obj_data = jsonable_encoder(db_obj)

        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field in obj_data:
            if field == 'modified':
                setattr(db_obj, field, datetime.now().astimezone().replace(microsecond=0))
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        # TODO: Check if this saves changes with the setattr calls
        await db_obj.save()
        return db_obj

    async def remove(self, *, id: str) -> ModelType | None:
        obj = await self.model.get(id)
        if obj:
            await obj.delete()
        return obj
