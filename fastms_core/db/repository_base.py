from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

ModelType = TypeVar('ModelType', bound=BaseModel)
ProjectionSchemaType = TypeVar('ProjectionSchemaType', bound=BaseModel)
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)
ListSchemaType = TypeVar('ListSchemaType', bound=BaseModel)
FindQueryProjectionType = TypeVar('FindQueryProjectionType', bound=BaseModel)


class AbstractRepository(ABC, Generic[ModelType, ListSchemaType, CreateSchemaType, UpdateSchemaType]):
    projection_schema: type[ProjectionSchemaType] = None

    @abstractmethod
    async def create(
        self, obj: CreateSchemaType, projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        pass

    @abstractmethod
    async def bulk_create(
        self, objs: list[CreateSchemaType], projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        pass

    @abstractmethod
    async def filter(
        self, query: dict[str, Any] | None = None, projection_schema: type[ProjectionSchemaType] | None = None
    ) -> list[ProjectionSchemaType]:
        pass

    @abstractmethod
    async def all(self, projection_schema: type[ProjectionSchemaType] | None = None) -> list[ProjectionSchemaType]:
        pass

    @abstractmethod
    async def get(
        self, query: Any, projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        pass

    @abstractmethod
    async def update(
        self, query: Any, obj: UpdateSchemaType, projection_schema: type[ProjectionSchemaType] | None = None
    ) -> ProjectionSchemaType:
        pass

    @abstractmethod
    async def delete(self, query: Any) -> int:
        pass

    @abstractmethod
    async def bulk_delete(self, query: list[Any]) -> int:
        pass
