from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, overload

from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

# from fastms_core.config import logger
from fastms_core.db.abc_repository import AbstractRepository
from fastms_core.db.exceptions import DuplicateKeyError, ObjectCreateError, ObjectNotFoundError, ObjectUpdateError
from fastms_core.db.mongo.schemas_base import PyObjectId

T = TypeVar('T', bound=BaseModel)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)
ModelType = TypeVar('ModelType', bound=BaseModel)


class BaseMongoRepository(AbstractRepository[T], Generic[T]):
    class Meta:
        collection_name: str

    def __init__(self, database: AsyncDatabase):
        super().__init__()
        self.__database: AsyncDatabase = database
        self.default_model: type[T] = self.__orig_bases__[0].__args__[0]  # type: ignore
        self.__validate()

    @property
    def collection(self) -> AsyncCollection:
        return self.__database[self.Meta.collection_name]

    def __validate(self) -> None:
        if 'id' not in self.default_model.model_fields:
            msg = 'Document class should have `id` field'
            raise Exception(msg)
        if not self.Meta.collection_name:
            msg = 'Meta should contain `collection_name`'
            raise Exception(msg)

    def _get_projection_from_model(self, model: type[ProjectionModel]) -> dict[str, Any]:
        projection = {}
        for field_name, field in model.model_fields.items():
            if field.annotation and issubclass(field.annotation, BaseModel):
                sub_model = field.annotation
                for sub_field_name in sub_model.model_fields:
                    projection[f'{field_name}.{sub_field_name}'] = 1
            else:
                projection[field_name] = 1

        return projection

    @overload
    async def find_one(self, query: dict[str, Any]) -> T: ...

    @overload
    async def find_one(self, query: dict[str, Any], projection_model: type[ProjectionModel]) -> ProjectionModel: ...

    async def find_one(
        self, query: dict[str, Any], projection_model: type[ProjectionModel] | None = None
    ) -> T | ProjectionModel | None:
        projection = self._get_projection_from_model(projection_model) if projection_model else None

        doc = await self.collection.find_one(filter=query, projection=projection)
        if not doc:
            return None

        return projection_model.model_validate(doc) if projection_model else self.default_model.model_validate(doc)

    @overload
    async def find_all(self, query: dict[str, Any] | None, limit: int, skip: int) -> list[T]: ...

    @overload
    async def find_all(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        projection_model: type[ProjectionModel],
    ) -> list[ProjectionModel]: ...

    async def find_all(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[T] | list[ProjectionModel]:
        projection = self._get_projection_from_model(projection_model) if projection_model else None
        result = self.collection.find(filter=query, projection=projection, limit=limit, skip=skip)
        if projection_model:
            return [projection_model.model_validate(doc) for doc in await result.to_list()]
            # return [projection_model.model_validate(doc) async for doc in result]
        else:
            return [self.default_model.model_validate(doc) for doc in await result.to_list()]

    async def count(self, query: dict[str, Any] | None = None) -> int:
        query = query or {}
        return await self.collection.count_documents(query)

    async def create(self, document: ModelType | dict[str, Any]) -> T:
        if isinstance(document, BaseModel):
            document = document.model_dump(exclude={'id'})  # probably don't need to exclude id

        # TODO (a.baikov): Move fields in Meta
        if 'created' in self.default_model.model_fields:
            document['created'] = datetime.now(UTC)
        if 'modified' in self.default_model.model_fields:
            document['modified'] = datetime.now(UTC)

        try:
            result = await self.collection.insert_one(document)
        except MongoDuplicateKeyError as e:
            raise DuplicateKeyError from e

        if not result.inserted_id:
            raise ObjectCreateError

        created = await self.collection.find_one({'_id': result.inserted_id})
        return self.default_model.model_validate(created)

    async def update(self, query: dict[str, Any], document: ModelType | dict[str, Any]) -> T:
        if isinstance(document, BaseModel):
            document = document.model_dump(exclude={'id'}, exclude_unset=True)

        if 'modified' in self.default_model.model_fields:
            document['modified'] = datetime.now(UTC)

        result = await self.collection.update_one(query, {'$set': document}, upsert=False)
        if result.modified_count == 0:
            raise ObjectUpdateError

        updated = await self.find_one(query)
        return updated

    async def delete(self, id: PyObjectId) -> int:
        exist = await self.count({'_id': id})
        if not exist:
            raise ObjectNotFoundError

        result = await self.collection.delete_one({'_id': id})
        return result.deleted_count
