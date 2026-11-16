from collections import defaultdict, deque
from typing import Any

from saltbox_core.minion_collections.schemas.collection_membership_run import (
    CollectionMembershipRun,
    CollectionSynchronizationModel,
)
from saltbox_core.minion_collections.utils.collection_filter import get_referenced_slugs
from saltbox_sdk.db.mongo.schemas_base import PyObjectId

ACTIVITY_FIELDS = {'last_activity', 'last_activity_seconds', 'is_not_active', 'is_never_active'}


def has_activity_filter(query: Any) -> bool:
    if isinstance(query, dict):
        return any(key in ACTIVITY_FIELDS or has_activity_filter(value) for key, value in query.items())
    if isinstance(query, list):
        return any(has_activity_filter(item) for item in query)
    return False


def get_activity_collection_ids(collections: list[CollectionSynchronizationModel]) -> set[PyObjectId]:
    ids_by_slug = {collection.slug: collection.id for collection in collections}
    dependents: dict[PyObjectId, set[PyObjectId]] = defaultdict(set)
    active = {collection.id for collection in collections if has_activity_filter(collection.query)}
    for collection in collections:
        dependencies = {ids_by_slug[slug] for slug in get_referenced_slugs(collection.query) if slug in ids_by_slug}
        if collection.parent_id is not None:
            dependencies.add(collection.parent_id)
        for dependency in dependencies:
            dependents[dependency].add(collection.id)
    pending = deque(active)
    while pending:
        for dependent in dependents[pending.popleft()] - active:
            active.add(dependent)
            pending.append(dependent)
    return active


def should_synchronize(runs: list[CollectionMembershipRun], every: int) -> bool:
    skipped = 0
    for run in sorted(runs, key=lambda item: (item.started_at, item.id), reverse=True):
        if run.status == 'succeeded':
            return skipped >= every - 1
        if run.status in {'started', 'failed'}:
            return True
        if run.status == 'skipped' and run.data.get('reason') == 'iteration_policy':
            skipped += 1
    return True
