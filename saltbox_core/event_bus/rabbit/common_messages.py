import enum

from pydantic import Field

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
