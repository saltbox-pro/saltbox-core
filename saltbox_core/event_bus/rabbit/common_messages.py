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
    task_args: list = Field(title='Task arguments', default_factory=list)
    task_kwargs: dict = Field(title='Task kwargs', default_factory=dict)


class RunTaskStatus(enum.Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'


class RunTaskResultEventBusMessage(EventBusBaseMessage):
    process_id: str
    status: RunTaskStatus
    data: dict
