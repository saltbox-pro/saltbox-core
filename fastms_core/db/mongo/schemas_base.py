from typing import Generic, TypeVar

from pydantic import BaseModel

SchemaType = TypeVar('SchemaType', bound=BaseModel)


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    total: int
    data: list[SchemaType]
