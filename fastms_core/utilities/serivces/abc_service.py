from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from fastms_core.db.abc_repository import AbstractRepository
from fastms_core.db.mongo.schemas_base import PaginatedResponse

Repository = TypeVar('Repository', bound=AbstractRepository)
ModelType = TypeVar('ModelType', bound=BaseModel)
ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class AbstractService(ABC, Generic[Repository]):
    def __init__(self, repo: Repository) -> None:
        self.repo: Repository = repo

    @abstractmethod
    async def get(self, *args: Any, **kwargs: Any) -> ModelType | ProjectionModel: ...

    @abstractmethod
    async def get_list(self, *args: Any, **kwargs: Any) -> list[ModelType] | list[ProjectionModel]: ...

    @abstractmethod
    async def get_list_paginated(
        self, *args: Any, **kwargs: Any
    ) -> PaginatedResponse[ModelType] | PaginatedResponse[ProjectionModel]: ...

    @abstractmethod
    async def count(self, *args: Any, **kwargs: Any) -> int: ...

    @abstractmethod
    async def exists(self, *args: Any, **kwargs: Any) -> int: ...

    @abstractmethod
    async def create(self, *args: Any, **kwargs: Any) -> ModelType | ProjectionModel: ...

    @abstractmethod
    async def update(self, *args: Any, **kwargs: Any) -> ModelType | ProjectionModel: ...

    @abstractmethod
    async def delete(self, *args: Any, **kwargs: Any) -> int: ...
