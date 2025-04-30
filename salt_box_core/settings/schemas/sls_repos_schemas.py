import uuid
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    UrlConstraints,
    field_serializer,
    model_validator,
)
from pydantic_core import Url
from slugify import slugify

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, TimezoneAwareDatetime

GitRepoUrl = Annotated[
    Url,
    UrlConstraints(max_length=2083, allowed_schemes=['http', 'https', 'git'], host_required=True),
]


class ReadOnlyFieldsShortMixin:
    repo_url: GitRepoUrl
    local_path: str = Field(max_length=50, pattern='(^[a-z0-9_-]+$)')
    last_synced: TimezoneAwareDatetime | None = None
    is_last_sync_successful: StrictBool = False
    last_sync_error: str | None = None

    @model_validator(mode='after')
    def check_repo_url(self) -> Self:
        if not self.repo_url.path or self.repo_url.path == '/':
            msg = 'Invalid repo_url: `path` part of url is required'
            raise ValueError(msg)
        return self


class ReadOnlyFieldsFullMixin(ReadOnlyFieldsShortMixin): ...


class EditableFieldsShortMixin:
    name: str = Field(min_length=3, max_length=100)
    description: str = Field(default='', max_length=500)
    is_active: StrictBool = Field(default=False)


class EditableFieldsFullMixin(EditableFieldsShortMixin):
    repo_user: str | None
    repo_pass: SecretStr | None
    branch: str | None = Field(default='master', max_length=100)


class CreateUpdateSerializerMixin:
    @field_serializer('repo_pass')
    def serialize_pass(self, pass_: SecretStr) -> str:
        return pass_.get_secret_value()


class SettingsSlsRepoCreateSchema(
    BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin
):
    local_path: str = Field(max_length=50, default='', pattern='(^[a-z0-9_-]+$|^$)')

    @field_serializer('repo_url')
    def serialize_url(self, url: GitRepoUrl) -> str:
        return url.unicode_string()

    @model_validator(mode='after')
    def validate_local_path(self) -> Self:
        if not self.local_path:
            repo_path = self.repo_url.path.strip('/').split('/')[-1] if self.repo_url.path else None
            repo_path = repo_path or str(uuid.uuid4())
            self.local_path = slugify(
                repo_path, lowercase=True, regex_pattern=r'[^a-z0-9_-]', separator='_', max_length=30
            )
        return self


class SettingsSlsRepoUpdateSchema(BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class SettingsSlsRepoShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class SettingsSlsRepoModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    pass
