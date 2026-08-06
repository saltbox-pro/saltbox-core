from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.config import SETTINGS
from saltbox_sdk.db.mongo.schemas_base import IDMixin, MongoQuery, MongoQueryField, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class TaskTemplateDefaultsSchema(BaseModel):
    batch_size: int | None = Field(title='Batch size', ge=0, default=None)
    max_jobs_count_at_same_time: int | None = Field(title='Max jobs count at same time', ge=1, default=None)
    max_retries: int | None = Field(title='Max retries', ge=0, default=None)
    retry_delay: int | None = Field(title='Retry delay', ge=0, default=None)
    ttl: int | None = Field(ge=0, le=SETTINGS.jobs_max_ttl, default=None)


class TaskTemplateCreateSchema(BaseModel):
    source_id: PyObjectId
    fun: str
    title: str | dict[str, str]
    description: str | dict[str, str] | None = None
    query: MongoQuery = MongoQueryField
    name: str = Field(title='Template name (Salt mods identifier)')
    sls_rel_path: str | None = Field(title='SLS file path relative to source root', default=None)
    schema_rel_path: str | None = Field(title='Schema file path relative to source root', default=None)
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    secret_pillars: list[str] | None = Field(title='Secret pillar names', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    i18n: dict[str, dict[str, str]] = Field(title='I18n dictionary', default_factory=dict)


class TaskTemplateFromRawCreateSchema(BaseModel):
    file_name: str = Field(
        title='File name (without path and extension)',
        pattern=r'^\w[\w-]*(?:\.[\w-]+)*(?:,\w[\w-]*(?:\.[\w-]+)*)*$',
    )
    content: str


class TaskTemplateFromRawUpdateSchema(BaseModel):
    content: str


class TaskTemplateUpdateSchema(BaseModel):
    pass


class TaskTemplateModel(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId = Field(title='Source ID')
    title: str | dict[str, str] = Field(title='Template title')
    description: str | dict[str, str] | None = Field(title='Template description', default=None)
    query: MongoQuery = MongoQueryField
    fun: str = Field(title='Salt function', examples=['state.apply'])
    # Имя = dot-path от serve root учётом namespace источника.
    # Используется напрямую как `mods` в `state.apply`.
    name: str = Field(title='Template name (Salt mods identifier)')
    sls_rel_path: str | None = Field(title='SLS file path relative to source root', default=None)
    schema_rel_path: str | None = Field(title='Schema file path relative to source root', default=None)
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    secret_pillars: list[str] | None = Field(title='Secret pillar names', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    i18n: dict[str, dict[str, str]] = Field(title='I18n dictionary', default_factory=dict)


class TaskTemplateAggregatedModel(TaskTemplateModel):
    local_path: str = Field(title='Source local path')
    source_root: str = Field(default='', title='Source root in the repository')


class TaskTemplateListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class TaskTemplatePublicSchema(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId
    title: str | dict[str, str]
    description: str | dict[str, str] | None = None
    query: MongoQuery = MongoQueryField
    fun: str
    name: str
    i18n: dict[str, dict[str, str]] = Field(default_factory=dict)


class TaskTemplatePublicWithContentSchema(TaskTemplatePublicSchema):
    sls_content: str


class TaskTemplateSchemasProjection(BaseModel):
    name: str
    json_schema: dict
    ui_schema: dict
    query: MongoQuery


class TaskTemplateSchemasListRequest(BaseModel):
    names: list[str] = Field(title='Template names')


class TaskTemplateSchemaResponse(BaseModel):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class TaskTemplateActions(StrEnum):
    LIST = 'list'
    READ = 'read'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
