from typing import ClassVar, TypedDict

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastms_core.db.mongo.schemas_base import MongoQueryBaseSchema
from fastms_core.minion_collections.schemas.minion_schemas import GrainsSchema, MinionSchema


class MinionFilterValuesBody(MongoQueryBaseSchema):
    collection_slug: str = Field(
        description='Collection slug',
        default='root',
    )
    field: str = Field(
        description='Field name to get unique values',
        examples=['grains.os', 'grains.cpu_model', 'grains.mem_total'],
        json_schema_extra={'example': 'grains.os'},
    )

    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}

    @field_validator('field')
    @classmethod
    def validate_field(cls, value: str) -> str:
        if '.' not in value and value not in MinionSchema.model_fields:
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
    value: str | None
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
    input_type: str = Field(serialization_alias='inputType')
