from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_serializer

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin


class ReadOnlyFieldsShortMixin:
    last_synced: datetime | None = None
    is_last_sync_successful: StrictBool = False
    last_sync_error: str | None = None


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    pass


class EditableFieldsShortMixin:
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default='', max_length=500)
    is_active: StrictBool = Field(default=False)


class EditableFieldsFullMixin(EditableFieldsShortMixin):
    repo_url: AnyUrl = Field(max_length=255)
    local_path: str | None = Field(max_length=50, default=None, pattern='^[a-z0-9_]+/$')
    repo_user: str | None
    repo_pass: SecretStr | None
    branch: str = Field(default='master', max_length=100)


class CreateUpdateSerializerMixin:
    @field_serializer('repo_url')
    def serialize_url(self, url: AnyUrl) -> str:
        return url.unicode_string()

    @field_serializer('repo_pass')
    def serialize_pass(self, pass_: SecretStr) -> str:
        return pass_.get_secret_value()


class SettingsSlsRepoCreateSchema(
    BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin
):
    pass


class SettingsSlsRepoUpdateSchema(BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class SettingsSlsRepoShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class SettingsSlsRepoModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass
