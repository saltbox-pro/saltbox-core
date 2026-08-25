from collections import defaultdict
from collections.abc import Callable
from typing import Annotated, TypeVar, cast

from fastapi import Depends
from pydantic import BaseModel
from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.schemas.collection import CollectionOrderOnlySchema
from saltbox_core.tasks.policy_ordering import PolicyOrderingItem, collection_order_path, order_ids_by_requirements
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository, get_task_minion_repository
from saltbox_core.tasks.schemas.task import TaskType
from saltbox_core.tasks.schemas.tasks_minion import (
    MinionPolicyGroupSchema,
    TaskMinionCreateSchema,
    TaskMinionForPolicySchema,
    TaskMinionModel,
    TaskMinionUpdateSchema,
)
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskMinionService(
    MongoBaseWithNotifyService[TaskMinionRepository, TaskMinionModel, TaskMinionCreateSchema, TaskMinionUpdateSchema]
):
    def __init__(
        self,
        repo: TaskMinionRepository,
        rdb: Redis,
    ):
        super().__init__(repo=repo, rdb=rdb)

        self.task_repository = TaskRepository(database=get_mongo_db())  # TODO (@): Temporary
        self.collection_repository = CollectionRepository(database=get_mongo_db())  # TODO (@): Temporary

    @property
    def notify_taskiq_task(self) -> Callable:
        return send_notify_by_mongo_service

    @property
    def service_name(self) -> str:
        return 'task_minion_service'

    def _get_notify_channel(self, obj: BaseModel, action: str) -> str | None:
        if not hasattr(obj, 'id') or not hasattr(obj, 'task_id'):
            return None

        return {
            'create': f'task:{obj.task_id}:task-minion:{obj.id}:create',
            'update': f'task:{obj.task_id}:task-minion:{obj.id}:update',
            'delete': f'task:{obj.task_id}:task-minion:{obj.id}:delete',
        }.get(action)

    async def run_notify(self, obj_id: PyObjectId, action: str) -> None:
        try:
            obj = await self.get(query=obj_id, projection_model=self.notify_schema)

            async with self.rdb.pipeline() as pipe:
                channel = self._get_notify_channel(obj=obj, action=action)

                if channel:
                    pipe.publish(channel=channel, message=self._prepare_pub_message(obj=obj))

                if action in ['create', 'update', 'delete'] and hasattr(obj, 'task_id'):
                    task = await self.task_repository.get(query=cast(PyObjectId, obj.task_id))
                    pipe.publish(channel=f'task:{obj.task_id}:update', message=self._prepare_pub_message(obj=task))

                await pipe.execute()
        except redis_exceptions.RedisError as e:
            logger.error(e)
        except ObjectNotFoundException:
            logger.debug(f'Object "{self.repo.Meta.collection_name}" for notifying not found by query: {obj_id}')

    async def get_collections_order_map(self) -> dict[PyObjectId, CollectionOrderOnlySchema]:
        collections = await self.collection_repository.get_list(query=None, projection_model=CollectionOrderOnlySchema)
        return {collection.id: collection for collection in collections}

    async def get_policies_for_minion(
        self,
        minion_inner_id: PyObjectId,
        *,
        collections_by_id: dict[PyObjectId, CollectionOrderOnlySchema] | None = None,
    ) -> list[TaskMinionForPolicySchema]:
        policies = await self.get_list(
            query={'minion_inner_id': minion_inner_id, 'task.task_type': TaskType.policy},
            projection_model=TaskMinionForPolicySchema,
        )

        if not policies:
            return []

        if collections_by_id is None:
            collections_by_id = await self.get_collections_order_map()

        groups: dict[PyObjectId, list[TaskMinionForPolicySchema]] = defaultdict(list)
        for policy in policies:
            groups[policy.target_collection.id].append(policy)

        ordered_collection_ids = sorted(
            groups.keys(), key=lambda collection_id: collection_order_path(collection_id, collections_by_id)
        )

        result: list[TaskMinionForPolicySchema] = []
        for collection_id in ordered_collection_ids:
            result.extend(self.__order_group_by_requirements(groups[collection_id]))

        return result

    @staticmethod
    def __order_group_by_requirements(
        policies: list[TaskMinionForPolicySchema],
    ) -> list[TaskMinionForPolicySchema]:
        by_task_id = {policy.task.id: policy for policy in policies}
        ordering_items = [
            PolicyOrderingItem(id=policy.task.id, weight=policy.task.weight, requirements=policy.task.requirements)
            for policy in policies
        ]

        return [by_task_id[task_id] for task_id in order_ids_by_requirements(ordering_items)]

    async def get_policy_groups_for_minion(
        self,
        minion_inner_id: PyObjectId,
        *,
        collections_by_id: dict[PyObjectId, CollectionOrderOnlySchema] | None = None,
    ) -> list[MinionPolicyGroupSchema]:
        policies = await self.get_policies_for_minion(
            minion_inner_id=minion_inner_id, collections_by_id=collections_by_id
        )

        groups: dict[PyObjectId, list[TaskMinionForPolicySchema]] = {}
        for policy in policies:
            groups.setdefault(policy.target_collection.id, []).append(policy)

        return [
            MinionPolicyGroupSchema(target_collection=group_policies[0].target_collection, policies=group_policies)
            for group_policies in groups.values()
        ]


def get_task_minion_service(
    repo: Annotated[TaskMinionRepository, Depends(get_task_minion_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> TaskMinionService:
    return TaskMinionService(
        repo=repo,
        rdb=rdb,
    )
