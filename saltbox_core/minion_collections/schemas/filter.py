from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryRefMixin
from saltbox_sdk.db.mongo.schemas_base import PipelineMongoQuery
from saltbox_sdk.exceptions import SaltBoxValidationException


class UniqueValuesBaseBody(BaseModel):
    collection_slug: str = Field(
        description='Collection slug',
        default='root',
    )
    query: PipelineMongoQuery = Field(
        default_factory=dict,
        title='MongoDB Query',
        description='A valid MongoDB query dictionary',
        examples=[
            {'grains.os': 'Ubuntu'},
            {'grains.cpu_model': {'$regex': 'Intel'}},
        ],
        json_schema_extra={'example': {'grains.cpu_model': {'$not': {'$regex': 'Intel'}}}},
    )
    skip: int = Field(strict=True, default=0, ge=0, le=1000)
    limit: int | None = Field(strict=True, default=None, ge=0, le=1000)

    model_config = ConfigDict(
        extra='forbid',
    )


class MinionFilterValuesBody(UniqueValuesBaseBody):
    field: str = Field(
        description='Field name to get unique values',
        examples=['grains.os', 'grains.cpu_model', 'grains.mem_total'],
        json_schema_extra={'example': 'grains.os'},
    )

    @field_validator('field')
    @classmethod
    def validate_field(cls, value: str) -> str:
        if any(not part or part.startswith('$') for part in value.split('.')):
            msg = f'Invalid field: {value}'
            raise SaltBoxValidationException(msg)

        return value


class ExtraFilterValuesBody(UniqueValuesBaseBody, ExtraDataCategoryRefMixin):
    field: str = Field(
        description='Extra data category field name to get unique values',
        examples=['room', 'serial_number'],
        json_schema_extra={'example': 'room'},
    )


class UniqueValueSchema(BaseModel):
    value: Any
    count: int


class UniqueValuesResponse(BaseModel):
    total: int
    data: list[UniqueValueSchema]


class MinionFilterOperatorsSchema(BaseModel):
    name: str
    value: str
    label: str


class MinionFilterSchema(BaseModel):
    name: str
    label: str
    operators: list[MinionFilterOperatorsSchema]
    input_type: str | None = Field(serialization_alias='inputType', default=None)
    value_editor_type: str | None = Field(serialization_alias='valueEditorType', default=None)
    default_value: bool | None = Field(serialization_alias='defaultValue', default=None)
    case_sensitive: bool | None = Field(serialization_alias='caseSensitive', default=None)


class FiltersActions(StrEnum):
    UNIQUE_GRAIN_VALUES = 'unique_grain_values'
    UNIQUE_EXTRA_VALUES = 'unique_extra_values'
    GET_SCHEMA = 'get_schema'
