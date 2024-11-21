from __future__ import annotations

from enum import Enum

from beanie import PydanticObjectId
from pydantic import BaseModel, Field


class FilterType(str, Enum):
    minion = "minion"


class FilterBaseSchema(BaseModel):

    title: str = Field(title='Title')
    type: FilterType = Field(title='Type')
    query: dict[str, str | dict] = Field(title='Query')


class FilterDBSchema(FilterBaseSchema):
    id: PydanticObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class FilterSchema(FilterDBSchema):
    pass


class FilterCreateSchema(FilterBaseSchema):
    pass


class FilterUpdateSchema(FilterBaseSchema):
    pass


class FilterListSchema(FilterDBSchema):
    pass


class FilterListQueryParams(BaseModel):
    page: int = Field(default=0, description='Page number', ge=0)
    per_page: int = Field(default=20, description='Items per page', ge=1)
