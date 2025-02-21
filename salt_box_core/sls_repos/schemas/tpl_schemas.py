from pydantic import BaseModel, ConfigDict, Field

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, PyObjectId


class ReadOnlyFieldsShortMixin:
    title: str = Field(title='Template title')
    name: str = Field(title='sls name')
    repo_id: PyObjectId = Field(title='Repository ID')
    commit_hash: str = Field(title='Commit hash')


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    json_schema: dict = Field(title='JSON schema')
    ui_schema: dict = Field(title='UI schema', default_factory=dict)


class EditableFieldsShortMixin: ...


class EditableFieldsFullMixin(EditableFieldsShortMixin): ...


class SlsTplCreateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    pass


class SlsTplUpdateSchema(BaseModel, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class SlsTplShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class SlsTplModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass
