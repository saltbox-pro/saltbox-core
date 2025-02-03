from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


class AbstractRepository(ABC, Generic[T]):
    @abstractmethod
    async def find_one(self, *args: Any, **kwargs: Any) -> T: ...

    @abstractmethod
    async def find_all(self, *args: Any, **kwargs: Any) -> list[T]: ...

    @abstractmethod
    async def count(self, *args: Any, **kwargs: Any) -> int: ...

    @abstractmethod
    async def create(self, *args: Any, **kwargs: Any) -> T: ...

    @abstractmethod
    async def update(self, *args: Any, **kwargs: Any) -> T: ...

    @abstractmethod
    async def delete(self, *args: Any, **kwargs: Any) -> int: ...
