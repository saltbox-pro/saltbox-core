from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar

import pydantic
from bson.errors import InvalidId
from bson.objectid import ObjectId
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    PlainSerializer,
    computed_field,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core.core_schema import (
    CoreSchema,
    no_info_plain_validator_function,
    plain_serializer_function_ser_schema,
    str_schema,
)

from salt_box_core.config import SETTINGS
from salt_box_core.utilities.helpers import format_iso8601_z

IS_PYDANTIC_V2_10 = int(pydantic.VERSION.split('.')[0]) >= 2 and int(pydantic.VERSION.split('.')[1]) >= 10
ALLOWED_MONGO_QUERY_KEYS = [
    '$and',
    '$or',
    '$nor',
    '$not',
    '$eq',
    '$ne',
    '$gt',
    '$gte',
    '$lt',
    '$lte',
    '$in',
    '$nin',
    '$exists',
    '$type',
    '$expr',
    '$jsonSchema',
    '$mod',
    '$regex',
    '$text',
    '$where',
    '$geoIntersects',
    '$geoWithin',
    '$geoNear',
    '$near',
    '$nearSphere',
    '$all',
    '$elemMatch',
    '$size',
    '$bitsAllClear',
    '$bitsAllSet',
    '$bitsAnyClear',
    '$bitsAnySet',
    '$comment',
    '$meta',
    '$slice',
]

SchemaType = TypeVar('SchemaType', bound=BaseModel)


def validate_mongo_query(value: dict[str, Any]) -> dict[str, Any]:
    for key, val in value.items():
        if key.startswith('$') and key not in ALLOWED_MONGO_QUERY_KEYS:
            msg = f'Invalid or unsupported operator `{key}`'
            raise ValueError(msg)
        if isinstance(val, dict):
            validate_mongo_query(val)

        if key in {'$and', '$or', '$in'} and not isinstance(val, list):
            msg = f'Value for `{key}` must be a `list`'
            raise ValueError(msg)
    return value


MongoQuery = Annotated[dict[str, Any], AfterValidator(validate_mongo_query)]
TimezoneAwareDatetime = Annotated[datetime, PlainSerializer(format_iso8601_z, when_used='json')]


class PyObjectId(ObjectId):
    """
    Object Id field. Compatible with Pydantic.
    """

    @classmethod
    def _validate(cls, v: Any) -> 'PyObjectId':
        if isinstance(v, bytes):
            v = v.decode('utf-8')
        try:
            return PyObjectId(v)
        except (InvalidId, TypeError):
            msg = 'Id must be of type PydanticObjectId'
            raise ValueError(msg) from None

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type[Any], handler: GetCoreSchemaHandler) -> CoreSchema:
        if not IS_PYDANTIC_V2_10:
            return no_info_plain_validator_function(
                cls._validate,
                metadata={
                    'pydantic_js_input_core_schema': str_schema(
                        pattern='^[0-9a-f]{24}$',
                        min_length=24,
                        max_length=24,
                    )
                },
                serialization=plain_serializer_function_ser_schema(
                    lambda instance: str(instance),
                    return_schema=str_schema(),
                    when_used='json',
                ),
            )
        return no_info_plain_validator_function(  # type: ignore[call-arg]
            cls._validate,
            json_schema_input_schema=str_schema(
                pattern='^[0-9a-f]{24}$',
                min_length=24,
                max_length=24,
            ),
            serialization=plain_serializer_function_ser_schema(
                lambda instance: str(instance),
                return_schema=str_schema(),
                when_used='json',
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            type='string',
            example='5eb7cf5a86d9755df3a6c593',
        )
        return json_schema


class IDMixin:
    id: PyObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class CreatedModifiedMixin:
    created: TimezoneAwareDatetime = Field(title='Created')
    modified: TimezoneAwareDatetime = Field(title='Modified')


class PaginatedResponse(BaseModel, Generic[SchemaType]):
    total: int = Field(description='Total number of items', ge=0)
    data: list[SchemaType] = Field(description='Items list')


# Deprecated, use SkipLimitParams instead
class PaginatedListParams(BaseModel):
    page: int = Field(default=0, description='Page number', ge=0)
    per_page: int = Field(default=20, description='Items per page', ge=1, examples=[20, 50, 100])


class SkipLimitParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)


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


class UserShort(BaseModel):
    sub: str
    name: str
    email: str


class TaskiqTaskIdResponse(BaseModel):
    task_id: str = Field(title='Taskiq task ID')
