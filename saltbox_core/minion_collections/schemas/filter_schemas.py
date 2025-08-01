from typing import ClassVar, TypedDict

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from saltbox_core.minion_collections.schemas.minion_schemas import GrainsSchema, MinionModel
from saltbox_sdk.db.mongo.schemas_base import PipelineMongoQuery


class MinionFilterValuesBody(BaseModel):
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
    field: str = Field(
        description='Field name to get unique values',
        examples=['grains.os', 'grains.cpu_model', 'grains.mem_total'],
        json_schema_extra={'example': 'grains.os'},
    )
    skip: int = Field(strict=True, default=0, ge=0, le=1000)
    limit: int | None = Field(strict=True, default=None, ge=0, le=1000)

    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}

    @field_validator('field')
    @classmethod
    def validate_field(cls, value: str) -> str:
        if '.' not in value and value not in MinionModel.model_fields:
            raise RequestValidationError(
                errors=[
                    {
                        'loc': ['body', 'field'],
                        'msg': f'Invalid field: {value}',
                        'type': 'value_error',
                        'input': value,
                    }
                ]
            )

        if '.' in value:
            field_name_chain = value.split('.')

            if field_name_chain[0] == 'grains' and field_name_chain[1] not in GrainsSchema.model_fields:
                raise RequestValidationError(
                    errors=[
                        {
                            'loc': ['body', 'field'],
                            'msg': f'Invalid field: {value}',
                            'type': 'value_error',
                            'input': value,
                        }
                    ]
                )
        return value


class GrainValue(TypedDict):
    value: str | int | None
    count: int


class UniqueGrainValuesResponse(BaseModel):
    total: int
    data: list[GrainValue]


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
