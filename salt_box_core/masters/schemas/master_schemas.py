from enum import Enum
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


def validate_ssh_pubkey_token(value: str) -> str:
    if not value.isascii() or ' ' in value:
        raise ValueError('Expected ASCII string with no space symbols')
    return value


def validate_is_ascii(value: str) -> str:
    if not value.isascii():
        raise ValueError('Expected ASCII string')
    return value


SshPubKeyToken = Annotated[str, AfterValidator(validate_ssh_pubkey_token)]
AsciiStr = Annotated[str, AfterValidator(validate_is_ascii)]


class SshPubKeyModel(BaseModel):
    type_name: SshPubKeyToken
    public_key: SshPubKeyToken
    comment: AsciiStr = ''

    def __str__(self) -> str:
        result = f'{self.type_name} {self.public_key}'
        if self.comment:
            result = f'{result} {self.comment}'
        return result

    @classmethod
    def from_str(cls, value: str) -> Self:
        tokens = value.split(' ', maxsplit=2)
        if 2 > len(tokens) > 3:
            raise ValueError('Unexpected OpenSSH public key string')
        try:
            comment = tokens[2]
        except IndexError:
            comment = ''
        return cls(type_name=tokens[0], public_key=tokens[1], comment=comment)


class MasterStatus(str, Enum):
    # TODO(a.karmanov): status to refresh keys (`revoked`?)
    new = 'new'
    accepted = 'accepted'
    rejected = 'rejected'


class MasterReadOnlyFieldsMixin:
    master_id: str = Field(title='Master ID', min_length=3)


class MasterSecretsMixin:
    # TODO(a.karmanov): make non-optional, reset with special master.status
    pubkey: str | None = Field(title='Public key', default=None)


class MasterSshPubkeysMixin:
    gitfs_pubkey: SshPubKeyModel
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
