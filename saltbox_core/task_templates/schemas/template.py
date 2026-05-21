from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_core.config import SETTINGS
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
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
    title: str
    description: str | dict[str, str] | None = None
    name: str = Field(title='Template name (Salt mods identifier)')
    sls_rel_path: str = Field(title='SLS file path relative to source root')
    # Хэш коммита (git) или контента (archive/inline) — для детектирования изменений
    source_hash: str | None = Field(title='Content hash / commit hash', default=None)
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    # secret_pillars: list[str] | None = Field(title='Secret pillar names', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class TaskTemplateFromRawCreateSchema(BaseModel):
    source_id: PyObjectId
    file_name: str = Field(title='File name (without path and extension)')
    content: str


class TaskTemplateUpdateSchema(BaseModel):
    pass


class TaskTemplateModel(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId = Field(title='Source ID')
    title: str = Field(title='Template title')
    description: str | dict[str, str] | None = Field(title='Template description', default=None)
    fun: str = Field(title='Salt function', examples=['state.apply'])
    # Имя = dot-path от serve root учётом namespace источника.
    # Используется напрямую как `mods` в `state.apply`.
    name: str = Field(title='Template name (Salt mods identifier)')
    sls_rel_path: str = Field(title='SLS file path relative to source root')
    # Хэш коммита (git) или контента (archive/inline) — для детектирования изменений
    source_hash: str | None = Field(title='Content hash / commit hash', default=None)
    defaults: TaskTemplateDefaultsSchema | None = Field(title='Default values', default=None)
    secret_pillars: list[str] | None = Field(title='Secret pillar names', default=None)
    json_schema: dict = Field(title='JSON schema', default_factory=dict)
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class TaskTemplateSyncSchema(BaseModel):
    source_id: PyObjectId
    name: str
    sls_rel_path: str
    source_hash: str


class TaskTemplateListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


class TaskTemplatePublicSchema(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId
    title: str
    description: str | dict[str, str] | None = None
    fun: str
    name: str


class TaskTemplateActions(StrEnum):
    LIST = 'list'
    READ = 'read'
    CREATE = 'create'
