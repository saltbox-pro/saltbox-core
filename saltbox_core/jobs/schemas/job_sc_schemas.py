from enum import StrEnum

from pydantic import BaseModel, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class ReadOnlyFieldsMixin:
    name: str = Field(title='Schema name')
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    commit_hash: str = Field(title='Commit hash')


class JobSchemaCreateSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JobSchemaUpdateSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JobSchemaShortSchema(BaseModel, CreatedModifiedMixin, IDMixin):
    name: str = Field(title='Schema name')
    commit_hash: str = Field(title='Commit hash')


class JobSchemaBaseSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JobSchemaModel(JobSchemaBaseSchema, CreatedModifiedMixin, IDMixin): ...


class JobSchemasActions(StrEnum):
    CLEAN = 'clean'
    LIST = 'list'
    SYNC = 'sync'
    READ = 'read'
