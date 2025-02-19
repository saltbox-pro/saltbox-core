from pydantic import BaseModel, Field

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin


class ReadOnlyFieldsMixin:
    name: str = Field(title='Schema name')
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    commit_hash: str = Field(title='Commit hash')


class JSONSchemaCreateSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JSONSchemaUpdateSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JSONSchemaShortSchema(BaseModel, CreatedModifiedMixin, IDMixin):
    name: str = Field(title='Schema name')
    commit_hash: str = Field(title='Commit hash')


class JSONSchemaBaseSchema(BaseModel, ReadOnlyFieldsMixin): ...


class JSONSchemaModel(JSONSchemaBaseSchema, CreatedModifiedMixin, IDMixin): ...


class JSONSchemaSyncResponse(BaseModel):
    created: list[str]
    updated: list[str]
    removed_count: int
    errors: list[str]
