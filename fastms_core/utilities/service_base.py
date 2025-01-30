from typing import Generic, TypeVar

from fastms_core.db.exceptions import ObjectNotFoundError
from fastms_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from fastms_core.db.repository_base import (
    AbstractRepository,
    CreateSchemaType,
    ListSchemaType,
    ModelType,
    ProjectionSchemaType,
    UpdateSchemaType,
)
from fastms_core.utilities.exceptions import ObjectDoesNotExistError, ServiceError

RepositoryType = TypeVar("RepositoryType", bound=AbstractRepository)


class BaseService(Generic[RepositoryType, ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    repository_class: type[RepositoryType]

    def __init__(self):
        if not self.repository_class:
            msg = 'Repository class must be defined'
            raise ServiceError(msg)

        self.repository = self.repository_class()

    async def create_obj(
            self, obj_data: CreateSchemaType, projection_schema: type[ProjectionSchemaType] = ModelType
    ) -> ProjectionSchemaType:
        obj: ProjectionSchemaType = await self.repository.create(
            obj=obj_data,
            projection_schema=projection_schema
        )

        return obj

    async def get_obj(
            self, obj_id: PyObjectId, projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType
    ) -> ProjectionSchemaType:
        try:
            return await self.repository.get(query=obj_id, projection_schema=projection_schema)
        except ObjectNotFoundError as e:
            msg = 'Object does not found'
            raise ObjectDoesNotExistError(msg) from e

    async def get_list(
            self,
            query: dict | None = None,
            start: int = 0,
            limit: int = 0,
            projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType
    ) -> list[ProjectionSchemaType]:
        if query is None:
            query = {}

        objs_list = await self.repository.filter(
            query=query, start=start, limit=limit, projection_schema=projection_schema
        )

        return objs_list

    async def get_all(
            self,
            start: int = 0,
            limit: int = 0,
            projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType
    ) -> list[ProjectionSchemaType]:
        objs_list = await self.repository.all(start=start, limit=limit, projection_schema=projection_schema)

        return objs_list

    async def get_list_paginated(
            self,
            page,
            per_page,
            query: dict | None = None,
            projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType
    ) -> PaginatedResponse[ProjectionSchemaType]:
        if query is None:
            query = {}

        objs = await self.get_list(
            query=query, start=page * per_page, limit=per_page, projection_schema=projection_schema
        )
        total = await self.repository.count(query=query)

        return PaginatedResponse[projection_schema](total=total, data=objs)

    async def update_obj(
            self,
            obj_id: PyObjectId,
            obj_data: UpdateSchemaType,
            projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType
    ) -> ProjectionSchemaType:
        try:
            updated_obj = await self.repository.update(query=obj_id, obj=obj_data, projection_schema=projection_schema)
        except ObjectNotFoundError as e:
            msg = 'Object does not found'
            raise ObjectDoesNotExistError(msg) from e

        return updated_obj

    async def delete_obj(self, obj_id: PyObjectId) -> int:
        try:
            deleted_count = await self.repository.delete(query=obj_id)
        except ObjectNotFoundError as e:
            msg = 'Object does not found'
            raise ObjectDoesNotExistError(msg) from e

        return deleted_count
