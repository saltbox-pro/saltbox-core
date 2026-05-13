from enum import StrEnum

from pydantic import BaseModel, Field

from saltbox_bridge_messages import SaltKeyStatusType


class SaltKeyActionEnum(StrEnum):
    accept = 'accept'
    reject = 'reject'
    delete = 'delete'


class SaltKeyToUpdateStatusEnum(StrEnum):
    accepted = 'accepted'
    rejected = 'rejected'


class SaltKeyMinion(BaseModel):
    minion_id: str
    salt_master: str


class SaltKeyMinionWithStatus(SaltKeyMinion):
    status: SaltKeyStatusType


class SaltKeyUpdateResultSchema(BaseModel):
    minions: list[SaltKeyMinion] = Field(default_factory=list)
    new_key_status: SaltKeyToUpdateStatusEnum


class SaltKeyListResultSchema(BaseModel): ...


# REST


class SaltKeyListRequestBody(BaseModel):
    masters: list[str] = Field(default_factory=list)
    status: SaltKeyStatusType | None = Field(default=None)


class SaltKeySetStatusRequestBody(BaseModel):
    minions: list[SaltKeyMinion] = Field(default_factory=list)


class SaltKeySetStatusToAllRequestBody(BaseModel):
    masters: list[str] = Field(default_factory=list)


# Permissions


class SaltKeyActions(StrEnum):
    ACCEPT = 'accept'
    REJECT = 'reject'
    DELETE = 'delete'
    LIST = 'list'
