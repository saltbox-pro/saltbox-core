from typing import Annotated, Any

from taskiq import TaskiqDepends

from saltbox_core.minion_collections.services.extra_data_collector import (
    ExtraDataCollectorService,
    get_extra_data_collector_service,
)
from saltbox_core.tkq import broker, queue_default
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@broker.task(queue_name=queue_default.name)
async def process_extra_collector_by_tgt(
    minion_id: str,
    salt_master: str,
    extra_collector_id: str,
    data: Any,
    extra_data_collector_service: Annotated[ExtraDataCollectorService, TaskiqDepends(get_extra_data_collector_service)],
) -> None:
    await extra_data_collector_service.process_data(
        minion_id=minion_id, salt_master=salt_master, collector_id=PyObjectId(extra_collector_id), data=data
    )


@broker.task(queue_name=queue_default.name)
async def process_extra_collector_by_id(
    minion_id: str,
    extra_collector_id: str,
    data: Any,
    extra_data_collector_service: Annotated[ExtraDataCollectorService, TaskiqDepends(get_extra_data_collector_service)],
) -> None:
    await extra_data_collector_service.process_data(
        minion_id=PyObjectId(minion_id), collector_id=PyObjectId(extra_collector_id), data=data
    )
