from pydantic import BaseModel, ConfigDict

from salt_box_core.masters.schemas.master_schemas import MasterStatus


class AuthMessage(BaseModel):
    master: str
    pubkey: str


class MasterStatusMessage(BaseModel):
    master: str
    status: MasterStatus
    is_pubkey_set: bool


class _BusMasterMessage(BaseModel):
    master: str

    model_config = ConfigDict(extra='allow')


class BusMasterMessage(_BusMasterMessage):
    model_config = ConfigDict(extra='ignore')
