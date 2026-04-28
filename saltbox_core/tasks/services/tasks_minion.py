from collections.abc import Callable
from typing import Annotated, TypeVar

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository, get_task_minion_repository
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema, TaskMinionModel, TaskMinionUpdateSchema
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

    @property
    def notify_taskiq_task(self) -> Callable:
        return send_notify_by_mongo_service

    @property
    def service_name(self) -> str:
        return 'task_minion_service'

    def _get_notify_channel(self, obj: TaskMinionModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'id') or not hasattr(obj, 'task_id'):
            return None

        return {
            'create': f'task:{obj.task_id}:task-minion:{obj.id}:create',
            'update': f'task:{obj.task_id}:task-minion:{obj.id}:update',
            'delete': f'task:{obj.task_id}:task-minion:{obj.id}:delete',
        }.get(action)

    # TODO (@): Temporary
    async def run_notify(self, obj_id: PyObjectId, action: str) -> None:
        obj = await self.get(query=obj_id)

        async with self.rdb.pipeline() as pipe:
            channel = self._get_notify_channel(obj=obj, action=action)

            if channel:
                pipe.publish(channel=channel, message=self._prepare_pub_message(obj=obj))

            if action in ['create', 'update', 'delete'] and hasattr(obj, 'task_id'):
                # TODO: skip for pillars v2 - can't get task_id in create method, because transaction is used
                try:
                    task = await self.task_repository.get(query=obj.task_id)
                    pipe.publish(channel=f'task:{obj.task_id}:update', message=self._prepare_pub_message(obj=task))
                except ObjectNotFoundException:
                    ...

            await pipe.execute()


def get_task_minion_service(
    repo: Annotated[TaskMinionRepository, Depends(get_task_minion_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> TaskMinionService:
    return TaskMinionService(
        repo=repo,
        rdb=rdb,
    )
