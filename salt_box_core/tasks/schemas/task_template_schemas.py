from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

# from salt_box_core.config import logger
from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, PaginatedListParams, PyObjectId


class ReadOnlyFieldsShortMixin:
    title: str = Field(title='Template title')
    name: str = Field(title='sls name')

    fun: str = Field(title='Salt fun', examples=['salt.ping'])

    repo_id: PyObjectId = Field(title='Repository ID')
    commit_hash: str = Field(title='Commit hash')


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class EditableFieldsShortMixin: ...


class EditableFieldsFullMixin(EditableFieldsShortMixin): ...


class TaskTemplateCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    pass


class TaskTemplateUpdateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class TaskTemplateShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class TaskTemplateModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass


class TaskTemplateListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
