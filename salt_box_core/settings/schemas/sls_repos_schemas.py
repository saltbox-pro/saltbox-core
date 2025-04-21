from typing import Self

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    field_serializer,
    model_validator,
)

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, TimezoneAwareDatetime


class ReadOnlyFieldsShortMixin:
    repo_url: AnyUrl = Field(max_length=255)
    local_path: str = Field(max_length=50, default='', pattern='(^[a-z0-9_-]+$|^$)')
    last_synced: TimezoneAwareDatetime | None = None
    is_last_sync_successful: StrictBool = False


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin):
    last_sync_error: str | None = None


class EditableFieldsShortMixin:
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default='', max_length=500)
    is_active: StrictBool = Field(default=False)


class EditableFieldsFullMixin(EditableFieldsShortMixin):
    repo_user: str | None
    repo_pass: SecretStr | None
    branch: str | None = Field(default='', max_length=100)


class CreateUpdateSerializerMixin:
    @field_serializer('repo_pass')
    def serialize_pass(self, pass_: SecretStr) -> str:
        return pass_.get_secret_value()


class SettingsSlsRepoCreateSchema(
    BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin
):
    @field_serializer('repo_url')
    def serialize_url(self, url: AnyUrl) -> str:
        return url.unicode_string()

    @model_validator(mode='after')
    def validate_local_path(self) -> Self:
        if not self.local_path:
            self.local_path = self.repo_url.unicode_string().rstrip('/').split('/')[-1].replace('.git', '')
        return self


class SettingsSlsRepoUpdateSchema(BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin):
    @model_validator(mode='after')
    def set_branch(self) -> Self:
        self.branch = self.branch or 'master'
        return self

    model_config = ConfigDict(
        extra='forbid',
    )


class SettingsSlsRepoShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class SettingsSlsRepoModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass
