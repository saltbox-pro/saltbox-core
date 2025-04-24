from collections.abc import Callable
from datetime import UTC, datetime
from inspect import isclass
from typing import Any, Generic, TypeVar, cast, overload

from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError
from pymongo.errors import OperationFailure

from salt_box_core.db.abc_repository import AbstractRepository
from salt_box_core.db.exceptions import (
    DuplicateKeyError,
    MultipleObjectsFoundError,
    ObjectCreateError,
    ObjectNotFoundError,
    ObjectUpdateError,
)
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.http_errors import BadRequest
from salt_box_core.utilities.helpers import recursive_replace_dates

T = TypeVar('T', bound=BaseModel)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)


class BaseMongoRepository(AbstractRepository[T], Generic[T]):
    class Meta:
        collection_name: str
        auto_now_add_fields: list[str]
        auto_now_fields: list[str]
        query_overrides: dict[str, str]

    def __init__(self, database: AsyncDatabase):
        super().__init__()
        self.__database: AsyncDatabase = database
        self.default_model: type[T] = self.__orig_bases__[0].__args__[0]  # type: ignore
        self.__validate()

    @property
    def __query_overrides__(self) -> dict[str, Callable]:
        query_overrides = {}

        if hasattr(self.Meta, 'query_overrides') and self.Meta.query_overrides:
            for override_name, override_callback_name in self.Meta.query_overrides.items():
                query_overrides[override_name] = getattr(self, override_callback_name)

        return query_overrides

    def __prepare_query__(self, query: PyObjectId | dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(query, PyObjectId):
            return {'_id': query}

        if query is None:
            return {}

        query_overrides = self.__query_overrides__

        def recursive_override(data: dict[str, Any]) -> dict[str, Any]:
            _query: dict[str, Any] = {}

            for data_key, data_value in data.items():
                if data_key in query_overrides.keys():
                    override_key, override_value = query_overrides[data_key](data_key, data_value)
                    if override_value is not None:
                        _query[override_key] = override_value
                else:
                    if isinstance(data_value, dict):
                        _query[data_key] = recursive_override(data_value)
                    # TODO (i.moshkov): check if this is correct
                    elif isinstance(data_value, list) and data_key not in ['$in', '$nin']:
                        _query[data_key] = [recursive_override(item_value) for item_value in data_value]
                    else:
                        _query[data_key] = data_value

            return _query

        if query_overrides:
            query = recursive_override(query)

        return cast(dict[str, Any], recursive_replace_dates(query))

    @property
    def collection(self) -> AsyncCollection:
        return self.__database[self.Meta.collection_name]

    def __validate(self) -> None:
        if 'id' not in self.default_model.model_fields:
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

    @staticmethod
    def _get_projection_from_model(model: type[ProjectionModel]) -> dict[str, Any]:
        projection = {}
        for field_name, field in model.model_fields.items():
            if field.annotation and isclass(field.annotation) and issubclass(field.annotation, BaseModel):
                sub_model = field.annotation
                for sub_field_name in sub_model.model_fields:
                    projection[f'{field_name}.{sub_field_name}'] = 1
            else:
                projection[field_name] = 1

        return projection

    @overload
    async def get(self, query: PyObjectId | dict[str, Any]) -> T: ...

    @overload
    async def get(
        self, query: PyObjectId | dict[str, Any], projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get(
        self, query: PyObjectId | dict[str, Any], projection_model: type[ProjectionModel] | None = None
    ) -> ProjectionModel | T:
        projection = self._get_projection_from_model(projection_model) if projection_model else None

        query = self.__prepare_query__(query)
        result = await self.collection.find(filter=query, projection=projection).to_list()

        if len(result) == 0:
            raise ObjectNotFoundError(obj_type=self.Meta.collection_name, query=query)
        elif len(result) > 1:
            raise MultipleObjectsFoundError

        data = result[0]

        if projection_model is not None:
            return projection_model.model_validate(data)
        else:
            return self.default_model.model_validate(data)

    @overload
    async def get_list(self, query: dict[str, Any] | None, limit: int, skip: int) -> list[T]: ...

    @overload
    async def get_list(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        projection_model: type[ProjectionModel],
    ) -> list[ProjectionModel]: ...

    async def get_list(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[T] | list[ProjectionModel]:
        projection = self._get_projection_from_model(projection_model) if projection_model else None
        query = self.__prepare_query__(query)
        result = self.collection.find(filter=query, projection=projection, limit=limit, skip=skip)

        if projection_model:
            return [projection_model.model_validate(doc) for doc in await result.to_list()]
            # return [projection_model.model_validate(doc) async for doc in result]
        else:
            return [self.default_model.model_validate(doc) for doc in await result.to_list()]

    async def count(self, query: dict[str, Any] | None = None) -> int:
        query = self.__prepare_query__(query)
        return await self.collection.count_documents(query)

    async def exists(self, query: dict[str, Any]) -> bool:
        query = self.__prepare_query__(query)
        return await self.collection.count_documents(query, limit=1) == 1

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
            data = data.model_dump(exclude={'id'})  # probably don't need to exclude id

        if hasattr(self.Meta, 'auto_now_add_fields') and self.Meta.auto_now_add_fields:
            for field in self.Meta.auto_now_add_fields:
                data[field] = datetime.now(UTC)
        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                data[field] = datetime.now(UTC)

        try:
            result = await self.collection.insert_one(data)
        except MongoDuplicateKeyError as e:
            raise DuplicateKeyError from e

        if not result.inserted_id:
            raise ObjectCreateError

        if projection_model:
            return await self.get(PyObjectId(result.inserted_id), projection_model=projection_model)
        else:
            return await self.get(PyObjectId(result.inserted_id))

    @overload
    async def update(
        self,
        query: PyObjectId | dict[str, Any],
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
    ) -> T: ...

    @overload
    async def update(
        self,
        query: PyObjectId | dict[str, Any],
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
        *,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def update(
        self,
        query: PyObjectId | dict[str, Any],
        data: ModelType | dict[str, Any],
        exclude_unset: bool = True,
        projection_model: type[ProjectionModel] | None = None,
    ) -> T | ProjectionModel:
        query = self.__prepare_query__(query)

        if isinstance(data, BaseModel):
            data = data.model_dump(exclude={'id'}, exclude_unset=exclude_unset)

        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                data[field] = datetime.now(UTC)

        result = await self.collection.update_one(query, {'$set': data}, upsert=False)
        if result.modified_count == 0:
            raise ObjectUpdateError

        if projection_model:
            return await self.get(query, projection_model=projection_model)
        else:
            return await self.get(query)

    async def delete(self, query: PyObjectId | dict[str, Any]) -> int:
        query = self.__prepare_query__(query)
        count = await self.count(query)

        if count == 0:
            raise ObjectNotFoundError(obj_type=self.Meta.collection_name, query=query)
        elif count > 1:
            raise MultipleObjectsFoundError

        result = await self.collection.delete_one(query)
        return result.deleted_count

    async def delete_many(self, query: dict[str, Any]) -> int:
        query = self.__prepare_query__(query)
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def aggregate(self, pipeline: list[dict]) -> list:
        try:
            cursor = await self.collection.aggregate(pipeline)
            return await cursor.to_list()
        except OperationFailure as e:
            msg = f'Error during pipeline execution in aggregate: {e}'
            raise BadRequest(detail=msg) from None
