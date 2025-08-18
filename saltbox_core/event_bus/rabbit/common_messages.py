import enum
from typing import ClassVar

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
    task_args: ClassVar[list] = []
    task_kwargs: ClassVar[dict] = {}


class RunTaskStatus(enum.Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'


class RunTaskResultEventBusMessage(EventBusBaseMessage):
    process_id: str
    status: RunTaskStatus
    data: dict
