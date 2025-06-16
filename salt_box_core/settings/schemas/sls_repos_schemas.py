import logging
import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Self

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
    ValidationError,
    field_serializer,
    model_validator,
)
from pydantic_core import Url
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from salt_box_core.config import SETTINGS
from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, TimezoneAwareDatetime

yaml = YAML()
logger = logging.getLogger(__name__)

class SlsRepoError(RuntimeError): ...
class SlsRepoManifestError(SlsRepoError): ...


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
    root: str = Field(default='', description='Path in repository supposed as Salt GitFS root')


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
        return url if isinstance(url, str) else os.fspath(url)

    @model_validator(mode='after')
    def validate_local_path(self) -> Self:
        if not self.local_path:
            self.local_path = os.fspath(uuid.uuid4().hex)

        return self


class SettingsSlsRepoUpdateSchema(BaseModel, CreateUpdateSerializerMixin, EditableFieldsFullMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class SettingsSlsRepoShortSchema(BaseModel, ReadOnlyFieldsShortMixin, EditableFieldsShortMixin, IDMixin):
    pass


class ManifestDigest(str, Enum):
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
    Path,
    AfterValidator(validate_path_bounds),
    AfterValidator(validate_path_is_not_absolute)
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
    def _set_global_values(self) -> Self:
        for file_entry in self.sshfs_files.values():
            if file_entry.checksum_type is FIELD_SENTINEL:
                file_entry.checksum_type = self.sshfs_files_checksum_type
            if file_entry.token is FIELD_SENTINEL:
                file_entry.token = self.sshfs_files_token
        return self


MANIFEST_FILE_ALLOWED_NAMES = ('manifest.yaml', 'manifest.yml')


class SettingsSlsRepoModel(BaseModel, CreatedModifiedMixin, EditableFieldsFullMixin, ReadOnlyFieldsFullMixin, IDMixin):
    @property
    def local_path_abs(self) -> Path:
        if not self.local_path:
            dosa = 'Empty local_path, uninitialized?'
            raise SlsRepoError(dosa)
        return Path(SETTINGS.local_repos_dir) / self.local_path

    def get_manifest_file(self) -> Path | None:
        for name in MANIFEST_FILE_ALLOWED_NAMES:
            path = self.local_path_abs / name
            if path.is_file():
                return path
        return None

    def parse_manifest(self) -> ManifestSchema:
        """
        :raises OSError: on filesystem operations errors
        :raises GitRepoManifestError:
        """
        path = self.get_manifest_file()
        if path is None:
            logger.warning("Not found manifest file in salt module repo '%s', using defaults", self.local_path_abs)
            return ManifestSchema()

        with path.open() as m_file:
            try:
                manifest_data = yaml.load(m_file)
            except ScannerError as err:
                raise SlsRepoManifestError(err) from None

        try:
            return ManifestSchema.parse_obj(manifest_data)
        except ValidationError as err:
            raise SlsRepoManifestError(err) from None
