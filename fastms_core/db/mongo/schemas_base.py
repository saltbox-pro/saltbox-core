from typing import Generic, TypeVar

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator

SchemaType = TypeVar('SchemaType', bound=BaseModel)


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    total: int
    data: list[SchemaType]


class PaginatedListQueryParams(BaseModel):
    page: int = Field(default=0, description='Page number', ge=0)
    per_page: int = Field(default=20, description='Items per page', ge=1, examples=[20, 50, 100])


class MongoQueryBaseSchema(BaseModel):
    query: dict = Field(
        title='Mongo query',
        description='Query dict must be a valid MongoDB query.',
        examples=[
            {'grains.os': 'Ubuntu'},
            {'grains.cpu_model': {'$regex': 'Intel'}},
        ],
        default={},
        validate_default=True,
        json_schema_extra={'example': {'grains.cpu_model': {'$not': {'$regex': 'Intel'}}}},
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, value: dict) -> dict:
        try:
            for k, v in value.items():
                if k in ['$and', '$or'] and not isinstance(v, list):
                    msg = 'Value of items with keys "$and" and "$or" must be a list'
                    raise ValueError(msg)
        except ValueError as e:
            raise RequestValidationError(
                errors=[
                    {
                        'loc': ['query', 'query'],
                        'msg': f'The query string must be a valid MongoDB query. Error:\n{e}',
                        'type': 'value_error',
                        'input': value,
                    }
                ]
            ) from None

        return value
