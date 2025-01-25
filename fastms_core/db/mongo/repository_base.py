import logging.config
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.new_config import get_mongo_db

ModelType = TypeVar('ModelType', bound=BaseModel)
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)
ListSchemaType = TypeVar('ListSchemaType', bound=BaseModel)
FindQueryProjectionType = TypeVar('FindQueryProjectionType', bound=BaseModel)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class AbstractRepository(ABC, Generic[ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    @abstractmethod
    async def add(self, document: CreateSchemaType) -> ModelType | None:
        pass

    @abstractmethod
    async def find_one(self, query: dict[str, Any]) -> ModelType | None:
        pass

    @abstractmethod
    async def find_all(self, query: dict[str, Any] | None = None) -> list[ModelType]:
        pass


# Реализация для MongoDB
class MongoDBRepository(AbstractRepository[ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    """A repository class for MongoDB operations"""

    def __init__(self, collection_name: str, model: type[ModelType]) -> None:
        self.db = get_mongo_db()
        self.collection = self.db[collection_name]
        self.model = model

    async def add(self, document: CreateSchemaType) -> ModelType | None:
        new_document = await self.collection.insert_one(document.model_dump(by_alias=True, exclude={'id'}))
        created_document = await self.collection.find_one({'_id': new_document.inserted_id})

        if not created_document:
            return None
        return self.model(**created_document)

    async def find_one(self, query: dict[str, Any]) -> ModelType | None:
        document = await self.collection.find_one(query)
        return self.model(**document) if document else None

    async def find_all(self, query: dict[str, Any] | None = None) -> list[ModelType]:
        documents = self.collection.find(query)
        return [self.model(**document) async for document in documents]

    async def get_paginated(
        self,
        search: dict | None = None,
        *,
        page: int = 0,
        per_page: int = 20,
        projection_query: dict | None = None,
    ) -> dict:
        if not search:
            search = {}

        data_query = self.collection.find(search, projection_query).skip(page * per_page).limit(per_page)
        data = [document async for document in data_query]
        logger.info('data: %s', data)
        total = await self.collection.count_documents(search)

        # TODO (a.baikov): think about returning PaginatedResponse[ListSchemaType] instead of dict
        # https://taiga.altlab.su/project/fastms/us/100
        # return PaginatedResponse[ListSchemaType](total=total, data=data)

        return {'total': total, 'data': data}
