from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

# from saltbox_core.config import logger
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class ReadOnlyFieldsShortMixin:
    title: str = Field(title='Template title')
    name: str = Field(title='sls name')
    fun: str = Field(title='Salt fun', examples=['salt.ping'])
    repo_id: PyObjectId = Field(title='Repository ID')
    commit_hash: str = Field(title='Commit hash')


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)
    sls_content: str = Field(title='SLS content')


class EditableFieldsShortMixin: ...


class EditableFieldsFullMixin(EditableFieldsShortMixin): ...


class TaskTemplateCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    pass


class TaskTemplateUpdateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class RepoInTaskTemplateSchema(BaseModel):
    name: str = Field(title='Repository name')
    repo_url: str = Field(title='Repository URL')


class TaskTemplateShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    repo_info: RepoInTaskTemplateSchema


class TaskTemplateModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass


class TaskTemplateListQueryParams(SkipLimitParams):
    repo_ids: list[PyObjectId] | None = None
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
