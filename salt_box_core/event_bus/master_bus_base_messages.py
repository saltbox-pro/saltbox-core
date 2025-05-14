from pydantic import BaseModel, ConfigDict

from salt_box_core.masters.schemas.master_schemas import MasterSshPubkeysMixin, MasterStatus


class AuthRequestMessage(BaseModel, MasterSshPubkeysMixin):
    master: str
    crypt_pubkey: str


class AuthResponseMessage(BaseModel):
    crypt_pubkey: str


class MasterStatusMessage(BaseModel):
    master: str
    status: MasterStatus
    is_pubkey_set: bool


class _BusMasterMessage(BaseModel):
    master: str

    model_config = ConfigDict(extra='allow')


class BusMasterMessage(_BusMasterMessage):
    model_config = ConfigDict(extra='ignore')
