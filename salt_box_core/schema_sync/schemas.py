from pydantic import BaseModel, Field

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin


class JSONSchemaReadOnlyFieldsMixin:
    name: str = Field(title='Schema name')
    content: dict = Field(title='Schema content')
    commit_hash: str = Field(title='Commit hash')


class JSONSchemaCreateSchema(BaseModel, JSONSchemaReadOnlyFieldsMixin): ...


class JSONSchemaShortSchema(BaseModel, CreatedModifiedMixin, IDMixin):
    name: str = Field(title='Schema name')
    commit_hash: str = Field(title='Commit hash')


class JSONSchemaModel(BaseModel, JSONSchemaReadOnlyFieldsMixin, CreatedModifiedMixin, IDMixin): ...
