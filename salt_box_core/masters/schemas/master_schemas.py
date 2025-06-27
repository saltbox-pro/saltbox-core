from pydantic import BaseModel, ConfigDict, Field
from saltbox_bridge_messages import MasterStatus, MasterSyncStatus, SshPubKeyModel

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, SkipLimitParams, TimezoneAwareDatetime


def validate_ssh_pubkey_token(value: str) -> str:
    if not value.isascii() or ' ' in value:
        msg = 'Expected ASCII string with no space symbols'
        raise ValueError(msg)
    return value


def validate_is_ascii(value: str) -> str:
    if not value.isascii():
        msg = 'Expected ASCII string'
        raise ValueError(msg)
    return value


class MasterReadOnlyFieldsMixin:
    master_id: str = Field(title='Master ID', min_length=3)


class MasterPubkeyMixin:
    pubkey: str = Field(description='Crypto public key of the Master')


class MasterSshPubkeysMixin:
    salt_conf_pubkey: SshPubKeyModel
    sshfs_pubkey: SshPubKeyModel


class MasterEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3)
    status: MasterStatus = Field(title='Status', default=MasterStatus.NEW)
    last_sync_timestamp: TimezoneAwareDatetime | None = None
    last_sync_status: MasterSyncStatus = MasterSyncStatus.NEVER


class MasterCreateSchema(
    BaseModel,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    MasterPubkeyMixin,
    MasterSshPubkeysMixin,
): ...


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin, MasterPubkeyMixin):
    model_config = ConfigDict(extra='ignore')


class MasterModel(
    BaseModel,
    CreatedModifiedMixin,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    MasterPubkeyMixin,
    MasterSshPubkeysMixin,
    IDMixin,
): ...


class MasterViewSchema(
    BaseModel,
    CreatedModifiedMixin,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    IDMixin
): ...


class MasterQueryParams(SkipLimitParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='forbid')
