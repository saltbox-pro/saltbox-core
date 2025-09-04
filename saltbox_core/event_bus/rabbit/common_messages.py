import enum
from typing import Any

from pydantic import BaseModel, Field

from saltbox_sdk.event_bus.schemas import EventBusBaseMessage


class SyncTemplatesRequestEventBusMessage(EventBusBaseMessage): ...


class SyncTemplatesResponseEventBusMessage(EventBusBaseMessage):
    name: str
    task_target: str
    fun: str

    json_schema: dict
    ui_schema: dict


class RunTaskEventBusMessage(EventBusBaseMessage):
    process_id: str
    fun: str
    data: dict = Field(title='Data', default_factory=dict)


class RunTaskStatus(enum.Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'


class RunTaskResultEventBusMessage(EventBusBaseMessage):
    process_id: str
    status: RunTaskStatus
    data: dict


class InventoryPutForMinion(BaseModel):
    minion_id: str
    master_id: str
    job_return: dict[str, Any]


class InventoryPutEventBusMessage(EventBusBaseMessage):
    minions: list[InventoryPutForMinion] = Field(title='Minions', default_factory=list)
    path: list[str | int] = Field(
        description='Path to data in job return, str for field, int for list index',
        examples=['return', 'module name', 'chages', 'ret'],
    )
