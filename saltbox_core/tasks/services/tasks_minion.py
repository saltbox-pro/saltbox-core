from typing import Annotated, TypeVar

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from saltbox_core.tasks.repositories.task import TaskRepository
from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository, get_task_minion_repository
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema, TaskMinionModel, TaskMinionUpdateSchema
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.redis.config import get_redis
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

    def _get_notify_channel(self, obj: TaskMinionModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'id') or not hasattr(obj, 'task_id'):
            return None

        return {
            'create': f'task:{obj.task_id}:task-minion:{obj.id}:create',
            'update': f'task:{obj.task_id}:task-minion:{obj.id}:update',
            'delete': f'task:{obj.task_id}:task-minion:{obj.id}:delete',
        }.get(action)

    # TODO (@): Temporary
    async def _notify(self, obj: BaseModel | ProjectionModel, action: str) -> None:
        await super()._notify(obj=obj, action=action)

        if action in ['create', 'update', 'delete'] and hasattr(obj, 'task_id'):
            task = await self.task_repository.get(query=obj.task_id)

            await self.rdb.publish(channel=f'task:{obj.task_id}:update', message=self._prepare_pub_message(obj=task))


def get_task_minion_service(
    repo: Annotated[TaskMinionRepository, Depends(get_task_minion_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> TaskMinionService:
    return TaskMinionService(
        repo=repo,
        rdb=rdb,
    )
