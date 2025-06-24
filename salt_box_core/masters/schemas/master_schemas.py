from pydantic import BaseModel, ConfigDict, Field, computed_field
from saltbox_bridge_messages import MasterStatus as MasterStatus
from saltbox_bridge_messages import SshPubKeyModel

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


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


class MasterSecretsMixin:
    # TODO (a.karmanov): make non-optional, reset with special master.status
    pubkey: str | None = Field(title='Public key', default=None)


class MasterSshPubkeysMixin:
    salt_conf_pubkey: SshPubKeyModel
    sshfs_pubkey: SshPubKeyModel


class MasterEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3)

    status: MasterStatus = Field(title='Status', default=MasterStatus.new)


class MasterCreateSchema(
    BaseModel,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    MasterSecretsMixin,
    MasterSshPubkeysMixin,
): ...


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin, MasterSecretsMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class MasterModel(
    BaseModel,
    CreatedModifiedMixin,
    MasterEditableFieldsMixin,
    MasterReadOnlyFieldsMixin,
    MasterSecretsMixin,
    MasterSshPubkeysMixin,
    IDMixin,
):
    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_pubkey_set(self) -> bool:
        return self.pubkey is not None


class MasterViewSchema(BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, IDMixin):
    pass


class MasterQueryParams(SkipLimitParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='forbid')
