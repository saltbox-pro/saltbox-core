from pydantic import BaseModel, Field

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin


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
