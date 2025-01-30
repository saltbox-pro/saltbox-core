from collections.abc import Mapping
from typing import Any, TypeVar, overload

from bson.objectid import ObjectId
from pymongo.asynchronous.cursor import AsyncCursor
from pymongo.results import (
    DeleteResult,
    InsertManyResult,
    InsertOneResult,
)

from fastms_core.db.exceptions import (
    MultipleObjectsFoundError,
    ObjCreationError,
    ObjectNotFoundError,
    RepositoryError,
)
from fastms_core.db.mongo.new_config import get_mongo_db
from fastms_core.db.mongo.schemas_base import PyObjectId
from fastms_core.db.repository_base import (
    AbstractRepository,
    CreateSchemaType,
    ListSchemaType,
    ModelType,
    ProjectionSchemaType,
    UpdateSchemaType,
)

DocumentType = TypeVar("DocumentType", bound=Mapping[str, Any])


class MongoDBBaseRepository(AbstractRepository[ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    """
    Base MongoDB repository class.
    """

    collection_name: str
    projection_schema = None
    id_field: str = 'id'
    collection_id_field: str = '_id'

    def __init__(self) -> None:
        if not self.projection_schema:
            msg = '"projection_schema" is required"'
            raise RepositoryError(msg)
        if not self.collection_name:
            msg = '"collection_name" is required'
            raise RepositoryError(msg)

        self.db = get_mongo_db()
        self.collection = self.db[self.collection_name]

    async def count(self, query: dict[str, Any] | None = None) -> int:
        return await self.collection.count_documents(filter=query)

    async def filter(
            self,
            query: dict[str, Any] | None = None,
            start: int = 0,
            limit: int = 0,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        documents: AsyncCursor[DocumentType] = self.collection.find(filter=query, skip=start, limit=limit)

        return await self.__project_documents(documents=documents, projection_schema=projection_schema)

    async def all(
            self,
            start: int = 0,
            limit: int = 0,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        return await self.filter(query={}, start=start, limit=limit, projection_schema=projection_schema)

    @overload
    async def get(
            self,
            query: dict[str, Any],
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    @overload
    async def get(
            self,
            query: str,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    @overload
    async def get(
            self,
            query: PyObjectId,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    async def get(
            self,
            query,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        if isinstance(query, str):
            document: DocumentType | None = await self.collection.find_one(
                {self.collection_id_field: PyObjectId(query)}
            )
        elif isinstance(query, PyObjectId | ObjectId):
            document: DocumentType | None = await self.collection.find_one({self.collection_id_field: query})
        elif isinstance(query, dict):
            documents: list[ProjectionSchemaType] = await self.filter(query=query, projection_schema=projection_schema)

            if not documents:
                raise ObjectNotFoundError

            if len(documents) > 1:
                raise MultipleObjectsFoundError

            return documents[0]
        else:
            msg = f'Invalid query type: {type(query)}'
            raise RepositoryError(msg)

        if not document:
            raise ObjectNotFoundError

        return await self.__project_document(document=document, projection_schema=projection_schema)

    async def create(
            self,
            obj: CreateSchemaType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        insert_result: InsertOneResult = await self.collection.insert_one(obj.model_dump(by_alias=True, exclude={'id'}))
        inserted_id = insert_result.inserted_id

        if inserted_id:
            return await self.get(query=inserted_id, projection_schema=projection_schema)

        raise ObjCreationError

    async def bulk_create(
            self,
            objs: list[CreateSchemaType],
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        insert_result: InsertManyResult = await self.collection.insert_many(
            documents=[obj.model_dump(by_alias=True, exclude={'id'}) for obj in objs]
        )

        return await self.filter(
            query={self.collection_id_field: {'$in': insert_result.inserted_ids}},
            projection_schema=projection_schema
        )

    @overload
    async def update(
            self,
            query: ModelType,
            obj: UpdateSchemaType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    @overload
    async def update(
            self,
            query: PyObjectId,
            obj: UpdateSchemaType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    @overload
    async def update(
            self,
            query: str,
            obj: UpdateSchemaType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        ...

    async def update(
            self,
            query,
            obj: UpdateSchemaType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        if type(query) in [str, dict, PyObjectId, ObjectId]:
            in_document = await self.get(query=query)
        elif type(query) is ModelType:
            in_document = await self.get(query={self.collection_id_field: getattr(query, self.id_field)})
        else:
            msg = f'Invalid query type: {type(query)}'
            raise RepositoryError(msg)

        await self.collection.update_one(
            filter={self.collection_id_field: getattr(in_document, self.id_field)},
            update={'$set': obj.model_dump(by_alias=True, exclude={'id'})}
        )

        return await self.get(query=getattr(in_document, self.id_field), projection_schema=projection_schema)

    @overload
    async def delete(self, query: ModelType) -> int:
        ...

    @overload
    async def delete(self, query: PyObjectId) -> int:
        ...

    @overload
    async def delete(self, query: str) -> int:
        ...

    @overload
    async def delete(self, query: dict[str, Any]) -> int:
        ...

    async def delete(self, query) -> int:
        try:
            if type(query) is ModelType:
                document = await self.get(
                    query={self.collection_id_field: PyObjectId(query.__getattr__(self.id_field))},
                    projection_schema=self.projection_schema
                )
            elif type(query) in [str, dict, PyObjectId, ObjectId]:
                document = await self.get(query=query, projection_schema=self.projection_schema)
            else:
                msg = 'Invalid query type'
                raise RepositoryError(msg)

            d_result: DeleteResult = await self.collection.delete_one(
                {self.collection_id_field: document.__getattr__(self.id_field)}
            )
        except ObjectNotFoundError:
            return -1

        return d_result.deleted_count

    @overload
    async def bulk_delete(self, query: list[ModelType]) -> int:
        ...

    @overload
    async def bulk_delete(self, query: list[PyObjectId]) -> int:
        ...

    @overload
    async def bulk_delete(self, query: list[str]) -> int:
        ...

    @overload
    async def bulk_delete(self, query: dict[str, Any]) -> int:
        ...

    async def bulk_delete(self, query) -> int:
        if isinstance(query, list) and all(type(i) is ModelType for i in query):
            _filter = {self.collection_id_field: {"$in": query}}
        elif isinstance(query, list) and all(isinstance(i, PyObjectId | ObjectId) for i in query):
            _filter = {self.collection_id_field: {"$in": query}}
        elif isinstance(query, list) and all(isinstance(i, str) for i in query):
            _filter = {self.collection_id_field: {"$in": [PyObjectId(_id) for _id in query]}}
        elif isinstance(query, dict):
            _filter = query
        else:
            msg = 'Invalid query type'
            raise RepositoryError(msg)

        d_result: DeleteResult = await self.collection.delete_many(filter=_filter)

        return d_result.deleted_count

    async def __project_document(
            self,
            document: DocumentType,
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType | None:
        if not projection_schema:
            projection_schema = self.projection_schema

        return projection_schema(**document) if document else None

    async def __project_documents(
            self,
            documents: AsyncCursor[DocumentType],
            projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        if not projection_schema:
            projection_schema = self.projection_schema

        return [projection_schema(**document) async for document in documents]
