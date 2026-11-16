import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from itertools import batched
from time import monotonic
from typing import Annotated

from fastapi import Depends
from redis.exceptions import RedisError

from saltbox_core.config import SETTINGS, logger
from saltbox_core.minion_collections.repositories.collection import CollectionRepository, get_collection_repository
from saltbox_core.minion_collections.repositories.collection_membership import (
    CollectionMembershipRepository,
    get_collection_membership_repository,
)
from saltbox_core.minion_collections.repositories.collection_membership_run import (
    CollectionMembershipRunRepository,
    get_collection_membership_run_repository,
)
from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.collection import CollectionBaseTreeModel
from saltbox_core.minion_collections.schemas.collection_membership import (
    CollectionMembershipCreateSchema,
    CollectionMembershipModel,
    CollectionMembershipUpdateSchema,
)
from saltbox_core.minion_collections.schemas.collection_membership_run import (
    CollectionMembershipRun,
    CollectionSynchronizationBranch,
    CollectionSynchronizationModel,
)
from saltbox_core.minion_collections.utils.membership_schedule import get_activity_collection_ids, should_synchronize
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.utilities.helpers import utc_now


class CollectionMembershipService(
    MongoBaseService[
        CollectionMembershipRepository,
        CollectionMembershipModel,
        CollectionMembershipCreateSchema,
        CollectionMembershipUpdateSchema,
    ]
):
    def __init__(
        self,
        repo: CollectionMembershipRepository,
        collection_repo: CollectionRepository,
        minion_repo: MinionRepository,
        run_repo: CollectionMembershipRunRepository,
    ) -> None:
        super().__init__(repo)
        self.collection_repo = collection_repo
        self.minion_repo = minion_repo
        self.run_repo = run_repo

    async def get_collection_synchronization_plan(self) -> dict[PyObjectId, bool]:
        collections = await self.collection_repo.get_list({}, projection_model=CollectionSynchronizationModel)
        existing_ids = {collection.id for collection in collections}
        deleted_ids = set(await self.repo.get_active_collection_ids()) - existing_ids
        activity_ids = get_activity_collection_ids(collections)
        plan = dict.fromkeys(existing_ids | deleted_ids, True)
        static_ids = list(existing_ids - activity_ids)
        if SETTINGS.membership_static_every_iterations == 1:
            return plan
        try:
            histories = await self.run_repo.get_lists(static_ids)
        except RedisError:
            logger.exception('Failed to read collection membership history; synchronizing all collections')
            return plan
        for collection_id, runs in histories.items():
            plan[collection_id] = should_synchronize(runs, SETTINGS.membership_static_every_iterations)
        return plan

    async def get_synchronization_branches(self, plan: dict[PyObjectId, bool]) -> list[CollectionSynchronizationBranch]:
        collections = await self.collection_repo.get_list({}, projection_model=CollectionSynchronizationModel)
        parents = {collection.id: collection.parent_id for collection in collections}
        branches = {
            collection_id: CollectionSynchronizationBranch(collection_id=str(collection_id))
            for collection_id, synchronize in plan.items()
            if synchronize
        }
        roots = []
        for collection_id, branch in branches.items():
            parent_id = parents.get(collection_id)
            parent = branches.get(parent_id) if parent_id is not None else None
            if parent is None:
                roots.append(branch)
            else:
                parent.children.append(branch)
        return roots

    async def synchronize_collection(
        self,
        collection_id: PyObjectId,
        renew_lock: Callable[[], Awaitable[bool]],
        parent_id: PyObjectId | None = None,
        parent_minion_ids: set[PyObjectId] | None = None,
    ) -> set[PyObjectId] | None:
        run = CollectionMembershipRun()
        start = monotonic()
        await self.save_run(collection_id, run)
        try:
            if not await renew_lock():
                msg = 'Collection membership execution lock was lost'
                raise RuntimeError(msg)
            try:
                collection = await self.collection_repo.get(collection_id, projection_model=CollectionBaseTreeModel)
            except ObjectNotFoundException:
                collection = None
            minion_ids = await self.get_matching_minion_ids(collection, parent_id, parent_minion_ids)
            await self.apply_membership(collection_id, minion_ids, run.started_at, renew_lock)
        except Exception as exc:
            run.status = 'failed'
            run.data = {'error': str(exc), 'error_type': type(exc).__name__}
            raise
        else:
            run.status = 'succeeded'
            run.data = {'minion_count': len(minion_ids)}
            return (
                minion_ids
                if collection is not None and len(minion_ids) <= SETTINGS.membership_parent_ids_limit
                else None
            )
        finally:
            if run.status != 'started':
                run.finished_at = utc_now()
                run.data['duration_ms'] = round((monotonic() - start) * 1000)
                await self.save_run(collection_id, run)

    async def get_matching_minion_ids(
        self,
        collection: CollectionBaseTreeModel | None,
        parent_id: PyObjectId | None,
        parent_minion_ids: set[PyObjectId] | None,
    ) -> set[PyObjectId]:
        if collection is None:
            return set()
        if (
            parent_minion_ids is not None
            and parent_id is not None
            and collection.parent_id == parent_id
            and len(parent_minion_ids) <= SETTINGS.membership_parent_ids_limit
        ):
            if not parent_minion_ids:
                return set()
            query = {'$and': [{'_id': {'$in': list(parent_minion_ids)}}, collection.query]}
        else:
            query = collection.full_query
        return set(await self.minion_repo.get_ids(query))

    async def save_run(self, collection_id: PyObjectId, run: CollectionMembershipRun) -> None:
        try:
            await self.run_repo.save(collection_id, run)
        except RedisError:
            logger.exception('Failed to save collection membership run for %s', collection_id)

    async def record_skipped_run(self, collection_id: PyObjectId, reason: str) -> None:
        now = utc_now()
        await self.save_run(
            collection_id,
            CollectionMembershipRun(status='skipped', started_at=now, finished_at=now, data={'reason': reason}),
        )

    async def apply_membership(
        self,
        collection_id: PyObjectId,
        minion_ids: set[PyObjectId],
        started_at: datetime,
        renew_lock: Callable[[], Awaitable[bool]],
    ) -> None:
        if not await renew_lock():
            msg = 'Collection membership execution lock was lost'
            raise RuntimeError(msg)
        async with asyncio.timeout(45), get_mongo_session_with_transaction() as session:
            active_ids = await self.repo.get_active_minion_ids(collection_id, session=session)
            for batch in batched(active_ids - minion_ids, 1000):
                await self.repo.close_intervals(collection_id, list(batch), started_at, session=session)
            for batch in batched(minion_ids - active_ids, 1000):
                data = [
                    CollectionMembershipCreateSchema(
                        collection_id=collection_id,
                        minion_inner_id=minion_id,
                        entered_at=started_at,
                    ).model_dump()
                    for minion_id in batch
                ]
                await self.repo.bulk_create(data, session=session)
            if not await renew_lock():
                msg = 'Collection membership execution lock was lost'
                raise RuntimeError(msg)


def get_collection_membership_service(
    repo: Annotated[CollectionMembershipRepository, Depends(get_collection_membership_repository)],
    collection_repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
    minion_repo: Annotated[MinionRepository, Depends(get_minion_repository)],
    run_repo: Annotated[CollectionMembershipRunRepository, Depends(get_collection_membership_run_repository)],
) -> CollectionMembershipService:
    return CollectionMembershipService(repo, collection_repo, minion_repo, run_repo)
