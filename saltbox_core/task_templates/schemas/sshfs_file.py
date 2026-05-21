from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_serializer, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class ManifestDigest(StrEnum):
    MD5 = 'md5'
    SHA256 = 'sha256'
    SHA512 = 'sha512'


class SshfsFileCreateSchema(BaseModel):
    source_id: PyObjectId
    rel_path: str
    url: HttpUrl
    checksum: str
    checksum_type: ManifestDigest = Field(default=ManifestDigest.SHA256, title='Checksum type')
    token: SecretStr | None
    unpack_as: Literal['bztar', 'gztar', 'tar', 'xztar', 'zip'] | None = Field(
        default=None,
        description='Unpack as arhive of specified format rather than place as is',
    )
    synced_on_sshfs: bool = Field(default=False, title='Whether the file currently exists on the SSHFS')
    last_sync_error: str | None = Field(default=None, title='Last error message if syncing to SSHFS failed')

    model_config = ConfigDict(extra='forbid')

    @field_serializer('token')
    def serialize_token(self, value: SecretStr | None) -> str | None:
        return value.get_secret_value() if value else None

    @field_serializer('url')
    def serialize_url(self, url: HttpUrl) -> str:
        return str(url)


class SshfsFileUpdateSchema(BaseModel):
    rel_path: str | None = None
    checksum: str | None = None
    checksum_type: ManifestDigest = Field(default=ManifestDigest.SHA256, title='Checksum type')
    token: SecretStr | None
    unpack_as: Literal['bztar', 'gztar', 'tar', 'xztar', 'zip'] | None = Field(
        default=None,
        description='Unpack as arhive of specified format rather than place as is',
    )

    model_config = ConfigDict(extra='forbid')

    @field_serializer('token')
    def serialize_token(self, value: SecretStr | None) -> str | None:
        return value.get_secret_value() if value else None


class SshfsFilePublicSchema(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId
    rel_path: str
    url: HttpUrl
    checksum: str
    checksum_type: ManifestDigest
    synced_on_sshfs: bool
    last_sync_error: str | None = Field(default=None, title='Last error message if syncing to SSHFS failed')


class SshfsFileModel(CreatedModifiedMixin, IDMixin):
    source_id: PyObjectId = Field(title='ID of the TemplateSource this file belongs to')
    rel_path: str = Field(title='File path relative to manifest root')
    url: HttpUrl
    checksum: str = Field(title='Checksum of the file on the url')
    checksum_type: ManifestDigest = Field(default=ManifestDigest.SHA256, title='Checksum type')
    token: SecretStr | None = Field(default=None, title='Token for accessing the file on the url')
    unpack_as: Literal['bztar', 'gztar', 'tar', 'xztar', 'zip'] | None = Field(
        default=None,
        description='Unpack as arhive of specified format rather than place as is',
    )
    synced_on_sshfs: bool = Field(default=False, title='Whether the file currently exists on the SSHFS')
    last_sync_error: str | None = Field(default=None, title='Last error message if syncing to SSHFS failed')

    model_config = ConfigDict(extra='forbid')


class FileInManifestSchema(BaseModel):
    rel_path: str | None = None
    url: HttpUrl
    checksum: str
    checksum_type: ManifestDigest | None = None
    token: SecretStr | None = None
    unpack_as: Literal['bztar', 'gztar', 'tar', 'xztar', 'zip'] | None = None

    model_config = ConfigDict(extra='forbid')


class ManifestSchema(BaseModel):
    root: str
    sshfs_files: dict[str, FileInManifestSchema]
    sshfs_files_checksum_type: ManifestDigest = ManifestDigest.SHA256
    sshfs_files_token: SecretStr | None = None

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def _set_global_values(self) -> 'ManifestSchema':
        for path, file_entry in self.sshfs_files.items():
            file_entry.checksum_type = file_entry.checksum_type or self.sshfs_files_checksum_type
            if not file_entry.token:
                file_entry.token = self.sshfs_files_token
            file_entry.rel_path = path
        return self


class SshfsFileActions(StrEnum):
    LIST = 'list'
