from typing import Any, Generic, TypeVar, overload

from pydantic import BaseModel

from fastms_core.db.mongo.repository_base import BaseMongoRepository
from fastms_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from fastms_core.utilities.serivces.abc_service import AbstractService

Repository = TypeVar('Repository', bound=BaseMongoRepository)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)
CreateSchema = TypeVar('CreateSchema', bound=BaseModel)
UpdateSchema = TypeVar('UpdateSchema', bound=BaseModel)


class MongoBaseService(AbstractService[Repository], Generic[Repository, ModelType, CreateSchema, UpdateSchema]):
    @overload
    async def get(self, query: dict[str, Any] | PyObjectId) -> ModelType: ...

    @overload
    async def get(
        self, query: dict[str, Any] | PyObjectId, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get(
        self, query: dict[str, Any] | PyObjectId, projection_model: type[ProjectionModel] | None = None
    ) -> ModelType | ProjectionModel:
        if isinstance(query, PyObjectId):
            query = {'_id': query}

        if projection_model:
            result = await self.repo.get(query=query, projection_model=projection_model)
        else:
            result = await self.repo.get(query=query)

        return result

    @overload
    async def get_list(self, query: Any, limit: int, skip: int) -> list[ModelType]: ...

    @overload
    async def get_list(
        self, query: Any, limit: int, skip: int, projection_model: type[ProjectionModel]
    ) -> list[ProjectionModel]: ...

    async def get_list(
        self, query: Any, limit: int = 0, skip: int = 0, projection_model: type[ProjectionModel] | None = None
    ) -> list[ModelType] | list[ProjectionModel]:
        if projection_model:
            return await self.repo.get_list(query=query, limit=limit, skip=skip, projection_model=projection_model)

        return await self.repo.get_list(query=query, limit=limit, skip=skip)

    @overload
    async def create(self, data: CreateSchema) -> ModelType: ...

    @overload
    async def create(self, data: CreateSchema, projection_model: type[ProjectionModel]) -> ProjectionModel: ...

    async def create(
        self, data: CreateSchema, projection_model: type[ProjectionModel] | None = None
    ) -> ModelType | ProjectionModel:
        if projection_model:
            result = await self.repo.create(data, projection_model=projection_model)
        else:
            result = await self.repo.create(data)

        return result

    @overload
    async def get_list_paginated(
        self, query: dict[str, Any] | None, limit: int, skip: int
    ) -> PaginatedResponse[ModelType]: ...

    @overload
    async def get_list_paginated(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        projection_model: type[ProjectionModel],
    ) -> PaginatedResponse[ProjectionModel]: ...

    async def get_list_paginated(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
    ) -> PaginatedResponse[ModelType] | PaginatedResponse[ProjectionModel]:
        total = await self.repo.count(query)

        if projection_model:
            data = await self.repo.get_list(query, limit=limit, skip=skip, projection_model=projection_model)
            return PaginatedResponse[ProjectionModel](total=total, data=data)
        else:
            data = await self.repo.get_list(query, limit=limit, skip=skip)
            return PaginatedResponse[ModelType](total=total, data=data)

    async def count(self, query: dict[str, Any] | None = None) -> int:
        return await self.repo.count(query)

    async def exists(self, query: dict[str, Any]) -> bool:
        return await self.repo.exists(query)

    @overload
    async def update(self, query: dict[str, Any] | PyObjectId, data: UpdateSchema) -> ModelType: ...

    @overload
    async def update(
        self, query: dict[str, Any] | PyObjectId, data: UpdateSchema, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: UpdateSchema,
        projection_model: type[ProjectionModel] | None = None,
    ) -> ModelType | ProjectionModel:
        if isinstance(query, PyObjectId):
            query = {'_id': query}

        if projection_model:
            result = await self.repo.update(query=query, data=data, projection_model=projection_model)
        else:
            result = await self.repo.update(query=query, data=data)

        return result

    async def delete(self, query: dict[str, Any] | PyObjectId) -> int:
        if isinstance(query, PyObjectId):
            query = {'_id': query}

        return await self.repo.delete(query)
