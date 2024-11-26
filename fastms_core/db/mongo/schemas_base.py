import json
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


class MongoQueryString(BaseModel):
    query: str = Field(
        description='Query string must be a valid JSON object representing a dictionary',
        examples=[
            '{"grains.os": "Ubuntu"}',
            '{"grains.cpu_model":{"$regex":"Intel"}}',
        ],
        default='{}',
        validate_default=True,
        json_schema_extra={'example': '{"grains.cpu_model":{"$not":{"$regex":"Intel"}}}'},
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, value: str) -> str:
        try:
            search = json.loads(value)
            if not isinstance(search, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            raise RequestValidationError(
                errors=[
                    {
                        'loc': ['query', 'query'],
                        'msg': 'The query string must be a valid JSON object representing a dictionary',
                        'type': 'value_error',
                        'input': value,
                    }
                ]
            ) from None
        return value
