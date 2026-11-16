from functools import partial
from typing import Any

from taskiq import TaskiqDepends

from saltbox_core.config import logger
from saltbox_core.event_bus.rabbit.exchanges import exchanges
from saltbox_core.minion_collections.schemas.collection_membership_run import CollectionSynchronizationBranch
from saltbox_core.minion_collections.services.collection_membership import (
    CollectionMembershipService,
    get_collection_membership_service,
)
from saltbox_core.tkq import broker, queue_default, queue_membership
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.event_bus.schemas import EventBusBaseMessage
from saltbox_sdk.event_bus.utils import send_message
from saltbox_sdk.utilities.taskiq import TaskAlreadyRunningException
from saltbox_sdk.utilities.taskiq_lock import UniqueTaskLock
from saltbox_sdk.utilities.taskiq_rabbit import get_unique_task_lock

MEMBERSHIP_LOCK_TTL = 120


@broker.task(
    queue_name=queue_default.name, schedule=[{'cron': '*/5 * * * *', 'labels': {'queue_name': queue_default.name}}]
)
async def request_extra_data_categories() -> None:
    logger.warning('request_extra_data_categories')
    await send_message(
        message=EventBusBaseMessage(sender='core'),
        exchange=exchanges['core_sync_extra_data_categories'],
    )


@broker.task(
    queue_name=queue_membership.name,
    unique_lock_timeout=MEMBERSHIP_LOCK_TTL,
    unique_execution_lock_timeout=MEMBERSHIP_LOCK_TTL,
    schedule=[{'cron': '* * * * *', 'labels': {'queue_name': queue_membership.name}}],
)
async def synchronize_collection_memberships(
    service: CollectionMembershipService = TaskiqDepends(get_collection_membership_service),
    unique_lock: UniqueTaskLock = TaskiqDepends(get_unique_task_lock),
) -> None:
    plan = await service.get_collection_synchronization_plan()
    renew = partial(unique_lock.renew_execution_lock, ttl=MEMBERSHIP_LOCK_TTL)
    for collection_id, synchronize in plan.items():
        if not await renew():
            msg = 'Collection membership dispatcher lock was lost'
            raise RuntimeError(msg)
        if not synchronize:
            await service.record_skipped_run(collection_id, 'iteration_policy')
    for branch in await service.get_synchronization_branches(plan):
        if not await renew():
            msg = 'Collection membership dispatcher lock was lost'
            raise RuntimeError(msg)
        await enqueue_membership_branch(branch, service)


async def enqueue_membership_branch(
    branch: CollectionSynchronizationBranch,
    service: CollectionMembershipService,
    parent_id: str | None = None,
    parent_minion_ids: list[str] | None = None,
) -> None:
    try:
        await synchronize_collection_membership.kiq(
            branch.collection_id,
            children=[child.model_dump() for child in branch.children],
            parent_id=parent_id,
            parent_minion_ids=parent_minion_ids,
        )
    except TaskAlreadyRunningException:
        await service.record_skipped_run(PyObjectId(branch.collection_id), 'already_queued_or_running')
        for child in branch.children:
            await enqueue_membership_branch(child, service)


@broker.task(
    queue_name=queue_membership.name,
    unique_kwargs=['collection_id'],
    unique_lock_timeout=MEMBERSHIP_LOCK_TTL,
    unique_execution_lock_timeout=MEMBERSHIP_LOCK_TTL,
)
async def synchronize_collection_membership(
    collection_id: str,
    children: list[dict[str, Any]] | None = None,
    parent_id: str | None = None,
    parent_minion_ids: list[str] | None = None,
    service: CollectionMembershipService = TaskiqDepends(get_collection_membership_service),
    unique_lock: UniqueTaskLock = TaskiqDepends(get_unique_task_lock),
) -> None:
    result = None
    try:
        result = await service.synchronize_collection(
            PyObjectId(collection_id),
            partial(unique_lock.renew_execution_lock, ttl=MEMBERSHIP_LOCK_TTL),
            parent_id=PyObjectId(parent_id) if parent_id is not None else None,
            parent_minion_ids={PyObjectId(value) for value in parent_minion_ids}
            if parent_minion_ids is not None
            else None,
        )
    finally:
        child_parent_minion_ids = [str(value) for value in result] if result is not None else None
        for child in children or []:
            await enqueue_membership_branch(
                CollectionSynchronizationBranch.model_validate(child),
                service,
                parent_id=collection_id,
                parent_minion_ids=child_parent_minion_ids,
            )
