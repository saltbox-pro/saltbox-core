from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.config import SETTINGS
from saltbox_sdk.db.mongo.schemas_base import IDMixin, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class JobSchemaReadOnlyFieldsMixin(BaseModel):
    name: str = Field(title='Schema name')


class JobSchemaEditableFieldsMixin(BaseModel):
    default_ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class JobSchemaCreateSchema(JobSchemaReadOnlyFieldsMixin, JobSchemaEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class JobSchemaUpdateSchema(JobSchemaEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class JobSchemaShortSchema(CreatedModifiedMixin, IDMixin):
    name: str = Field(title='Schema name')


class JobSchemaBaseSchema(JobSchemaReadOnlyFieldsMixin, JobSchemaEditableFieldsMixin): ...


class JobSchemaModel(JobSchemaBaseSchema, CreatedModifiedMixin, IDMixin): ...


# System


class JobSchemaTTLOnlySchema(IDMixin):
    default_ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


class JobSchemaJSONSchemaOnlySchema(IDMixin):
    json_schema: dict = Field(title='JSON schema')


# REST


class JobSchemaListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


# Permissions


class JobSchemasActions(StrEnum):
    CLEAN = 'clean'
    LIST = 'list'
    SYNC = 'sync'
    READ = 'read'
