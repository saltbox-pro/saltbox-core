from collections import defaultdict
from typing import NamedTuple

from saltbox_core.minion_collections.schemas.collection import CollectionOrderOnlySchema
from saltbox_core.tasks.schemas.task import TaskRequirement, TaskRequirementResultType
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionStatus
from saltbox_core.tasks.schemas.tasks_status import ACTIVE_TASK_STATUSES, TaskStatus
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class PolicyOrderingItem(NamedTuple):
    id: PyObjectId
    weight: int
    requirements: list[TaskRequirement]


def order_ids_by_requirements(items: list[PolicyOrderingItem]) -> list[PyObjectId]:
    by_id = {item.id: item for item in items}
    dependents: dict[PyObjectId, list[PyObjectId]] = defaultdict(list)
    in_degree: dict[PyObjectId, int] = dict.fromkeys(by_id, 0)

    for item in items:
        for requirement in item.requirements:
            if requirement.task_id not in by_id:
                continue

            dependents[requirement.task_id].append(item.id)
            in_degree[item.id] += 1

    ready = sorted(
        (item_id for item_id, degree in in_degree.items() if degree == 0),
        key=lambda item_id: by_id[item_id].weight,
    )
    ordered: list[PyObjectId] = []

    while ready:
        current_id = ready.pop(0)
        ordered.append(current_id)

        newly_ready = []
        for dependent_id in dependents.get(current_id, []):
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                newly_ready.append(dependent_id)

        ready.extend(newly_ready)
        ready.sort(key=lambda item_id: by_id[item_id].weight)

    if len(ordered) != len(items):
        ordered_ids = set(ordered)
        leftovers = [item_id for item_id in by_id if item_id not in ordered_ids]
        ordered.extend(sorted(leftovers, key=lambda item_id: by_id[item_id].weight))

    return ordered


def collection_order_path(
    collection_id: PyObjectId, collections_by_id: dict[PyObjectId, CollectionOrderOnlySchema]
) -> tuple[int, ...]:
    path: list[int] = []
    current_id: PyObjectId | None = collection_id
    seen: set[PyObjectId] = set()

    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        collection = collections_by_id.get(current_id)
        if collection is None:
            break

        path.append(collection.order)
        current_id = collection.parent_id

    return tuple(reversed(path))


QUEUE_RESOLVED_STATUSES = (TaskMinionStatus.success, TaskMinionStatus.failed, TaskMinionStatus.unreachable)


def is_active_predecessor(task_status: TaskStatus | None, minion_status: TaskMinionStatus) -> bool:
    if task_status not in ACTIVE_TASK_STATUSES:
        return False

    if task_status == TaskStatus.stopping:
        return minion_status == TaskMinionStatus.in_work

    return True


class PolicyExecutionInfo(NamedTuple):
    task_id: PyObjectId
    status: TaskMinionStatus
    requirements: list[TaskRequirement]


def resolve_execution_status(
    task_id: PyObjectId, ordered_policies: list[PolicyExecutionInfo]
) -> TaskMinionStatus | None:
    index = next((i for i, policy in enumerate(ordered_policies) if policy.task_id == task_id), None)

    if index is None:
        return None

    predecessors = ordered_policies[:index]
    if any(predecessor.status not in QUEUE_RESOLVED_STATUSES for predecessor in predecessors):
        return TaskMinionStatus.blocked

    statuses_by_task_id = {policy.task_id: policy.status for policy in ordered_policies}

    for requirement in ordered_policies[index].requirements:
        actual_status = statuses_by_task_id.get(requirement.task_id)
        satisfied = {
            TaskRequirementResultType.only_success: actual_status == TaskMinionStatus.success,
            TaskRequirementResultType.only_failed: actual_status == TaskMinionStatus.failed,
            TaskRequirementResultType.any: actual_status in (TaskMinionStatus.success, TaskMinionStatus.failed),
        }[requirement.result_type]

        if not satisfied:
            return TaskMinionStatus.unreachable

    return TaskMinionStatus.pending
