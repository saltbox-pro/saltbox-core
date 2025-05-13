import json
from typing import Any, Generic, TypeVar, overload

from pydantic import BaseModel

from salt_box_core.db.redis.repository_sortedset_base import SortedsetRedisRepository
from salt_box_core.db.redis.schemas_base import SortedSetId
from salt_box_core.db.schemas_base import CursoredResponse, PaginatedResponse
from salt_box_core.utilities.serivces.abc_service import AbstractService

Repository = TypeVar('Repository', bound=SortedsetRedisRepository)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)
CreateSchema = TypeVar('CreateSchema', bound=BaseModel)
UpdateSchema = TypeVar('UpdateSchema', bound=BaseModel)


class RedisSortedsetBaseService(
    AbstractService[Repository], Generic[Repository, ModelType, CreateSchema, UpdateSchema]
):
    @overload
    async def get(self, query: SortedSetId | int | float) -> ModelType: ...

    @overload
    async def get(
        self, query: SortedSetId | int | float, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get(
        self, query: SortedSetId | int | float, projection_model: type[ProjectionModel] | None = None
    ) -> ModelType | ProjectionModel:
        if projection_model:
            result = await self.repo.get(query=query, projection_model=projection_model)
        else:
            result = await self.repo.get(query=query)

        return result

    @overload
    async def get_list(
        self, start: int, end: int | None, limit: int | None, skip: int, desc: bool
    ) -> list[ModelType]: ...

    @overload
    async def get_list(
        self,
        start: int,
        end: int | None,
        limit: int | None,
        skip: int,
        desc: bool,
        projection_model: type[ProjectionModel],
    ) -> list[ProjectionModel]: ...

    async def get_list(
        self,
        start: int = 0,
        end: int | None = None,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[ModelType] | list[ProjectionModel]:
        if projection_model:
            return await self.repo.get_list(
                start=start, end=end, limit=limit, skip=skip, desc=desc, projection_model=projection_model
            )

        return await self.repo.get_list(start=start, end=end, limit=limit, skip=skip, desc=desc)

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
        self, start: int, end: int, limit: int | None, skip: int, desc: bool
    ) -> PaginatedResponse[ModelType]: ...

    @overload
    async def get_list_paginated(
        self,
        start: int,
        end: int | None,
        limit: int | None,
        skip: int,
        desc: bool,
        projection_model: type[ProjectionModel],
    ) -> PaginatedResponse[ProjectionModel]: ...

    async def get_list_paginated(
        self,
        start: int = 0,
        end: int | None = None,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
        projection_model: type[ProjectionModel] | None = None,
    ) -> PaginatedResponse[ModelType] | PaginatedResponse[ProjectionModel]:
        total = await self.repo.count(start=start, end=end)

        if projection_model:
            data = await self.repo.get_list(
                start=start, end=end, limit=limit, skip=skip, desc=desc, projection_model=projection_model
            )
        else:
            data = await self.repo.get_list(start=start, end=end, limit=limit, skip=skip, desc=desc)

        return PaginatedResponse(total=total, data=data)

    async def get_list_cursored(
        self,
        start: int | float,
        end: int | float | None = None,
        cursor: int = 0,
        count: int = 100,
        match: str | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> CursoredResponse[ModelType] | CursoredResponse[ProjectionModel]:
        data = []

        async def load_data() -> int:
            raw_data = await self.repo.zscan(cursor=cursor, match=match, count=count)

            for raw_obj_data in raw_data[1]:
                score = raw_obj_data[1]

                if (end and start < score < end) or (end is None and start < score):
                    obj_data = json.loads(raw_obj_data[0])
                    if projection_model:
                        data.append(projection_model.model_validate(obj_data))
                    else:
                        data.append(self.repo.default_model.model_validate(obj_data))

            return raw_data[0]

        while len(data) < count:
            cursor = await load_data()

            if cursor == 0:
                break

        return CursoredResponse(next_cursor=cursor, data=data)

    async def count(self, start_id: SortedSetId | int | float | None, end_id: SortedSetId | int | float | None) -> int:
        return await self.repo.count(start=start_id, end=end_id)

    async def exists(self, query: SortedSetId) -> bool:
        return await self.repo.exists(query)

    @overload
    async def update(
        self,
        query: SortedSetId,
        data: UpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
    ) -> ModelType: ...

    @overload
    async def update(
        self,
        query: SortedSetId,
        data: UpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
        *,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def update(
        self,
        query: SortedSetId,
        data: UpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
        *,
        projection_model: type[ProjectionModel] | None = None,
    ) -> ModelType | ProjectionModel:
        if projection_model:
            result = await self.repo.update(
                query=query, data=data, projection_model=projection_model, exclude_unset=exclude_unset
            )
        else:
            result = await self.repo.update(query=query, data=data, exclude_unset=exclude_unset)

        return result

    async def delete(self, query: SortedSetId) -> int:
        return await self.repo.delete(query)
