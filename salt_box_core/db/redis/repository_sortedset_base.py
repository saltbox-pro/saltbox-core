import json
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, overload

from pydantic import BaseModel
from redis.asyncio import Redis

# from salt_box_core.config import logger
from salt_box_core.db.abc_repository import AbstractRepository
from salt_box_core.db.exceptions import (
    MultipleObjectsFoundError,
    ObjectNotFoundError,
    ObjectUpdateError,
)
from salt_box_core.db.redis.schemas_base import SortedSetId

T = TypeVar('T', bound=BaseModel)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)


class SortedsetRedisRepository(AbstractRepository[T], Generic[T]):
    class Meta:
        collection_name: str
        id_field_name: str = 'id'
        auto_now_add_fields: list[str]
        auto_now_fields: list[str]
        query_overrides: dict[str, str]

    def __init__(self, database: Redis):
        super().__init__()
        self._database: Redis = database
        self.default_model: type[T] = self.__orig_bases__[0].__args__[0]  # type: ignore
        self.__validate()

    def __validate(self) -> None:
        if self.Meta.id_field_name not in self.default_model.model_fields:
            msg = 'Document class should have `id` field'
            raise Exception(msg)
        if not hasattr(self.Meta, 'collection_name') or not self.Meta.collection_name:
            msg = 'Meta should contain `collection_name`'
            raise Exception(msg)
        if hasattr(self.Meta, 'auto_now_add_fields') and self.Meta.auto_now_add_fields:
            for field in self.Meta.auto_now_add_fields:
                if field not in self.default_model.model_fields:
                    msg = f'Meta `auto_now_add_fields` `{field}` should be in model fields'
                    raise Exception(msg.format(field, self.Meta.collection_name))
        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                if field not in self.default_model.model_fields:
                    msg = f'Meta `auto_now_fields` `{field}` should be in model fields'
                    raise Exception(msg.format(field, self.Meta.collection_name))

    @classmethod
    def __generate_id(cls) -> SortedSetId:
        return datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')

    @overload
    async def get(self, query: SortedSetId | int | float) -> T: ...

    @overload
    async def get(
        self, query: SortedSetId | int | float, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get(
        self, query: SortedSetId | int | float, projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | T:
        result = await self._database.zrange(
            name=self.Meta.collection_name,
            start=int(query),
            end=int(query),
            byscore=True,
        )

        if type(query) in [int, float]:
            query = str(query)

        if len(result) == 0:
            raise ObjectNotFoundError(obj_type=self.Meta.collection_name, query={'id': query})
        elif len(result) > 1:
            raise MultipleObjectsFoundError

        data = json.loads(result[0].decode())
        data['id'] = query

        if projection_model is not None:
            return projection_model.model_validate(data)
        else:
            return self.default_model.model_validate(data)

    @overload
    async def get_list(self, start: int, end: int | None, limit: int | None, skip: int) -> list[T]: ...

    @overload
    async def get_list(
        self, start: int, end: int | None, limit: int | None, skip: int, projection_model: type[ProjectionModel]
    ) -> list[ProjectionModel]: ...

    async def get_list(
        self,
        start: int = 0,
        end: int | None = None,
        limit: int | None = None,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[T] | list[ProjectionModel]:
        _result = await self._database.zrange(
            name=self.Meta.collection_name,
            start=start,
            end=-1 if end is None else end,
            offset=skip,
            num=limit,
            withscores=True,
            byscore=True,
        )

        result = [{'id': str(int(obj[1])), **json.loads(obj[0].decode())} for obj in _result]

        if projection_model:
            return [projection_model.model_validate(obj) for obj in result]
        else:
            return [self.default_model.model_validate(obj) for obj in result]

    async def count(
        self, start: SortedSetId | int | float | None = None, end: SortedSetId | int | float | None = None
    ) -> int:
        return await self._database.zcount(
            name=self.Meta.collection_name,
            min=start if start else float('-inf'),
            max=end if end else float('inf'),
        )

    async def exists(self, query: SortedSetId) -> bool:
        return await self._database.zcount(name=self.Meta.collection_name, min=int(query), max=int(query)) == 1

    @overload
    async def create(self, data: ModelType | dict[str, Any]) -> T: ...

    @overload
    async def create(
        self, data: ModelType | dict[str, Any], projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def create(
        self,
        data: ModelType | dict[str, Any],
        projection_model: type[ProjectionModel] | None = None,
    ) -> T | ProjectionModel:
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude={'id'}, mode='json')  # probably don't need to exclude id
        else:
            if 'id' in data.keys():
                del data['id']

        obj_id: SortedSetId = self.__generate_id()

        if hasattr(self.Meta, 'auto_now_add_fields') and self.Meta.auto_now_add_fields:
            for field in self.Meta.auto_now_add_fields:
                data[field] = datetime.now(UTC).timestamp()
        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                data[field] = datetime.now(UTC).timestamp()

        await self._database.zadd(
            name=self.Meta.collection_name,
            mapping={json.dumps(data): int(obj_id)},
        )

        if projection_model:
            return await self.get(obj_id, projection_model=projection_model)
        else:
            return await self.get(obj_id)

    @overload
    async def update(
        self,
        query: SortedSetId,
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
    ) -> T: ...

    @overload
    async def update(
        self,
        query: SortedSetId,
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
        *,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def update(
        self,
        query: SortedSetId,
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
        projection_model: type[ProjectionModel] | None = None,
    ) -> T | ProjectionModel:
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude={'id'}, exclude_unset=exclude_unset, mode='json')

        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                data[field] = datetime.now(UTC)

        await self.get(query=query)
        await self.delete(query=query)

        updated_count = await self._database.zadd(
            name=self.Meta.collection_name,
            mapping={json.dumps(data): int(query)},
        )

        if updated_count != 1:
            raise ObjectUpdateError

        if projection_model:
            return await self.get(query, projection_model=projection_model)
        else:
            return await self.get(query)

    async def delete(self, query: SortedSetId) -> int:
        await self.get(query=query)
        await self._database.zrem(self.Meta.collection_name, query)

        return 1
