from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.config import SETTINGS
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class TaskTemplateDefaultsSchema(BaseModel):
    batch_size: int = Field(title='Batch size', ge=0)
    max_jobs_count_at_same_time: int = Field(title='Max jobs count at some time', ge=1)
    max_retries: int = Field(title='Max retries', ge=0)
    retry_delay: int = Field(title='Retry delay', ge=0)
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


class TaskTemplateDefaultsInputSchema(BaseModel):
    batch_size: int | None = Field(title='Batch size', ge=0, default=None)
    max_jobs_count_at_same_time: int | None = Field(title='Max jobs count at some time', ge=1, default=None)
    max_retries: int | None = Field(title='Max retries', ge=0, default=None)
    retry_delay: int | None = Field(title='Retry delay', ge=0, default=None)
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


class ReadOnlyFieldsShortMixin:
    name: str = Field(title='SLS name')
    repo_id: PyObjectId = Field(title='Repository ID')


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin): ...


class EditableFieldsShortMixin:
    title: str = Field(title='Template title')
    description: str | dict[str, str] | None = Field(title='Template description', default=None)
    fun: str = Field(title='Salt fun', examples=['salt.ping'])
    commit_hash: str = Field(title='Commit hash')


class EditableFieldsFullMixin(EditableFieldsShortMixin):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    sls_content: str = Field(title='SLS content')


class TaskTemplateCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    defaults: TaskTemplateDefaultsInputSchema | None = Field(title='Default values', default=None)


class TaskTemplateUpdateSchema(BaseModel, EditableFieldsFullMixin):
    defaults: TaskTemplateDefaultsInputSchema | None = Field(title='Default values', default=None)

    model_config = ConfigDict(extra='ignore')


class RepoInTaskTemplateSchema(BaseModel):
    name: str = Field(title='Repository name')
    repo_url: str = Field(title='Repository URL')


class TaskTemplateShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    defaults: TaskTemplateDefaultsSchema = Field(title='Default values')
    repo_info: RepoInTaskTemplateSchema


class TaskTemplateModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    defaults: TaskTemplateDefaultsSchema = Field(title='Default values')


class TaskTemplateListBody(SkipLimitParams, QueryParams, SortParams):
    repo_ids: list[PyObjectId] | None = None

    model_config = ConfigDict(extra='ignore')


class TaskTemplatesActions(StrEnum):
    READ = 'read'
    LIST = 'list'
