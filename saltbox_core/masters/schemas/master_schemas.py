from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_bridge_messages import MasterStatus, MasterSyncStatus, SshPubKeyModel
from saltbox_sdk.db.mongo.schemas_base import IDMixin, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime


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
    MasterSshPubkeysMixin,
): ...


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class MasterModel(
    BaseModel,
    CreatedModifiedMixin,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    MasterSshPubkeysMixin,
    IDMixin,
): ...


class MasterMasterIdOnlySchema(BaseModel, IDMixin):
    master_id: str = Field(title='Master ID')


# REST


class MasterViewSchema(
    BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, IDMixin
): ...


class MasterListBody(SkipLimitParams, QueryParams, SortParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='ignore')


# Permissions


class MastersActions(StrEnum):
    LIST = 'list'
    READ = 'read'
    ACCEPT = 'accept'
    REJECT = 'reject'
