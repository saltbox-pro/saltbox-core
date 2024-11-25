from typing import Any

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from fastms_core.db.mongo.schemas_base import PaginatedListQueryParams


class TargetTemplateBaseSchema(BaseModel):
    name: str = Field(title='Name')
    tgt: str = Field(title='Target')
    tgt_type: str = Field(title='Target Type')
    # filter:


class TargetTemplateInDBSchema(TargetTemplateBaseSchema):
    id: PydanticObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class TargetTemplateSchema(TargetTemplateInDBSchema): ...


class TargetTemplateCreateSchema(TargetTemplateBaseSchema): ...


class TargetTemplateUpdateSchema(TargetTemplateBaseSchema): ...


class TargetTemplateListSchema(TargetTemplateInDBSchema): ...


class TaskTemplateBaseSchema(BaseModel):
    name: str = Field(title='Name')
    fun: str = Field(title='Function')
    arg: list[Any] | None = Field(title='Arguments', default=None)
    kwarg: dict[Any, Any] | None = Field(title='Keyword Arguments', default=None)


class TaskTemplateInDBSchema(TaskTemplateBaseSchema):
    id: PydanticObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class TaskTemplateSchema(TaskTemplateInDBSchema): ...


class TaskTemplateCreateSchema(TaskTemplateBaseSchema): ...


class TaskTemplateUpdateSchema(TaskTemplateBaseSchema): ...


class TaskTemplateListSchema(TaskTemplateInDBSchema): ...


class TaskTemplateListQueryParams(PaginatedListQueryParams): ...
