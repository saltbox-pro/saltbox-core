from typing import Any

from pydantic import BaseModel, ConfigDict

from salt_box_core.event_bus.maater_bus_base_messages import BusMasterMessage


class NewJobMessage(BusMasterMessage):
    hash_name: str


class CreateJobMessage(BusMasterMessage):
    tgt: str
    tgt_type: str
    fun: str
    arg: list
    kwarg: dict
    jid: str | None = None


class JobReturn(BaseModel):
    ret: Any
    retcode: int
    jid: str

    model_config = ConfigDict(extra='allow')


class JobSyncMessage(BusMasterMessage):
    jid: str
    tgt: str
    tgt_type: str
    fun: str
    arg: list
    kwarg: dict
    returns: dict[str, JobReturn]
