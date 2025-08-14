import logging
import os
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from git.types import PathLike
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Extra,
    Field,
    HttpUrl,
    SecretStr,
    StrictBool,
    UrlConstraints,
    field_serializer,
    model_validator,
)
from pydantic_core import Url

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime

logger = logging.getLogger(__name__)


GitRepoUrl = Annotated[
    Url,
    UrlConstraints(max_length=2083, allowed_schemes=['http', 'https', 'git'], host_required=True),
]


class ReadOnlyFieldsShortMixin:
    repo_url: PathLike
    local_path: str = Field(max_length=32, default='', pattern='(^[a-z0-9_-]+$|^$)')
    last_synced: TimezoneAwareDatetime | None = None
    is_last_sync_successful: StrictBool = False
    last_sync_error: str | None = None
    locked: bool | None = None
    root: str = Field(default='', description='Path in repository to serve for masters')

    def get_repo_url_as_str(self) -> str:
        return os.fspath(self.repo_url)


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
    @field_serializer('repo_url')
    def serialize_url(self, url: PathLike) -> str:
        return self.get_repo_url_as_str()

    @model_validator(mode='after')
    def validate_local_path(self) -> 'SettingsSlsRepoCreateSchema':
        if not self.local_path:
            self.local_path = uuid.uuid4().hex
        return self


class SettingsSlsRepoUpdateSchema(BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class SettingsSlsRepoShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class ManifestDigest(StrEnum):
    MD5 = 'md5'
    SHA256 = 'sha256'
    SHA512 = 'sha512'


DEFAULT_DIGEST = ManifestDigest.SHA256
FIELD_SENTINEL: Any = object()


def validate_path_is_not_absolute(value: Path) -> Path:
    """value must be a relative Path"""
    if value.is_absolute():
        msg = 'Path must be relative'
        raise ValueError(msg)
    return value


def validate_path_bounds(value: Path) -> Path:
    str_val = os.path.normpath(value)
    if str_val.startswith('../'):
        msg = 'Relative path leads outisde'
        raise ValueError(msg)
    return Path(str_val)


def validate_digest(value: str) -> str:
    return ManifestDigest(value).value


NotAbsolutePath = Annotated[Path, AfterValidator(validate_path_is_not_absolute)]
SafeNotAbsoultePath = Annotated[
    Path, AfterValidator(validate_path_bounds), AfterValidator(validate_path_is_not_absolute)
]
ManifestDigestStr = Annotated[str, AfterValidator(validate_digest)]


class ManifestSshfsFilesSchema(BaseModel):
    url: HttpUrl
    checksum: str
    checksum_type: ManifestDigestStr = FIELD_SENTINEL
    token: str | None = FIELD_SENTINEL
    unpack: bool = Field(default=False, description='Unpack arhive rather than processing as a regular file')

    class Config:
        extra = Extra.forbid


class ManifestSchema(BaseModel):
    root: SafeNotAbsoultePath = Path()
    sshfs_files: dict[NotAbsolutePath, ManifestSshfsFilesSchema] = {}
    sshfs_files_checksum_type: ManifestDigestStr = DEFAULT_DIGEST.value
    sshfs_files_token: str | None = None

    class Config:
        extra = Extra.forbid

    @model_validator(mode='after')
    def _set_global_values(self) -> 'ManifestSchema':
        for file_entry in self.sshfs_files.values():
            if file_entry.checksum_type is FIELD_SENTINEL:
                file_entry.checksum_type = self.sshfs_files_checksum_type
            if file_entry.token is FIELD_SENTINEL:
                file_entry.token = self.sshfs_files_token
        return self


class SettingsSlsRepoModel(
    BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin
): ...
