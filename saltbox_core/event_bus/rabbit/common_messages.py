from typing import Any

from pydantic import BaseModel, Field

from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema
from saltbox_sdk.event_bus.schemas import EventBusBaseMessage


class RunJobRequestEventBusMessage(EventBusBaseMessage):
    data: JobCreateSchema


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
