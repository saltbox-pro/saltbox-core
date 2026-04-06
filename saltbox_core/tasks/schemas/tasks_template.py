from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.config import SETTINGS
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class TaskTemplateDefaultsSchema(BaseModel):
    batch_size: int | None = Field(title='Batch size', ge=0, default=None)
    max_jobs_count_at_same_time: int | None = Field(title='Max jobs count at some time', ge=1, default=None)
    max_retries: int | None = Field(title='Max retries', ge=0, default=None)
    retry_delay: int | None = Field(title='Retry delay', ge=0, default=None)
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


class ReadOnlyFieldsShortMixin:
    name: str = Field(title='SLS name')
    repo_id: PyObjectId | None = Field(title='Repository ID', default=None)


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin): ...


class EditableFieldsShortMixin:
    title: str = Field(title='Template title')
    description: str | dict[str, str] | None = Field(title='Template description', default=None)
    fun: str = Field(title='Salt fun', examples=['salt.ping'])
    commit_hash: str | None = Field(title='Commit hash', default=None)


class EditableFieldsFullMixin(EditableFieldsShortMixin):
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    secret_pillars: list[str] | None = Field(title='List of secret pillar names', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    sls_content: str | None = Field(title='SLS content', default=None)


class TaskTemplateCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin): ...


class TaskTemplateUpdateSchema(BaseModel, EditableFieldsFullMixin):
    model_config = ConfigDict(extra='ignore')


class RepoInTaskTemplateSchema(BaseModel):
    name: str = Field(title='Repository name')
    repo_url: str = Field(title='Repository URL')


class TaskTemplateShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    defaults: TaskTemplateDefaultsSchema = Field(title='Default values')
    repo_info: RepoInTaskTemplateSchema | None = Field(title='Repository info', default=None)


class TaskTemplateModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin): ...


class TaskTemplateExcludeSlsSchema(BaseModel, CreatedModifiedMixin, ReadOnlyFieldsFullMixin, IDMixin):
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class TaskTemplateListBody(SkipLimitParams, QueryParams, SortParams):
    repo_ids: list[PyObjectId] | None = None

    model_config = ConfigDict(extra='ignore')


class TaskTemplateSchemasListRequest(BaseModel):
    names: list[str] = Field(title='Template names')


class TaskTemplateSchemaResponse(BaseModel):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class TaskTemplateSchemasProjection(BaseModel):
    name: str
    json_schema: dict
    ui_schema: dict


class TaskTemplatesActions(StrEnum):
    READ = 'read'
    LIST = 'list'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
