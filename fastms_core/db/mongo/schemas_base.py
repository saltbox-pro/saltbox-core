from typing import Any, Generic, TypeVar

from bson.errors import InvalidId
from bson.objectid import ObjectId
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    computed_field,
    field_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from pydantic_core.core_schema import (
    CoreSchema,
    ValidationInfo,
)

from fastms_core.config import SETTINGS

SchemaType = TypeVar('SchemaType', bound=BaseModel)


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _: ValidationInfo):
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        try:
            return PyObjectId(v)
        except (InvalidId, TypeError) as e:
            msg = "Id must be of type PyObjectId"
            raise ValueError(msg) from e

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.json_or_python_schema(
            python_schema=core_schema.with_info_plain_validator_function(cls.validate),
            json_schema=core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: str(instance), when_used="json"
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            type="string",
            example="679a94c460223560cc63b024",
        )
        return json_schema


class BaseDBSchema(BaseModel):
    id: PyObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    total: int = Field(description='Total number of items', default=0, ge=0)
    data: list[SchemaType] = Field(description='Items list', default=[])


class PaginatedListParams(BaseModel):
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


class AccessModel(BaseModel):
    roles: list[str] = Field(default=[])


class User(BaseModel):
    sub: str  # = Field(serialization_alias='id')
    resource_access: dict[str, AccessModel] | None = Field(default=None, exclude=True)
    email_verified: bool
    name: str
    email: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def roles(self) -> list[str]:
        client_roles: list[str] = []
        if self.resource_access:
            try:
                client_roles = self.resource_access[SETTINGS.keycloak_client].roles
            except KeyError:
                pass

        return client_roles
