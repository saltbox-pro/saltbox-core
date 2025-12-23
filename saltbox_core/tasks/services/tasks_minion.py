from typing import Annotated, TypeVar

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository, get_task_minion_repository
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema, TaskMinionModel, TaskMinionUpdateSchema
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskMinionService(
    MongoBaseWithNotifyService[TaskMinionRepository, TaskMinionModel, TaskMinionCreateSchema, TaskMinionUpdateSchema]
):
    def _get_notify_channel(self, obj: TaskMinionModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'id') or not hasattr(obj, 'task_id'):
            return None

        return {
            'create': f'task:{obj.task_id}:task-minion:{obj.id}:create',
            'update': f'task:{obj.task_id}:task-minion:{obj.id}:update',
            'delete': f'task:{obj.task_id}:task-minion:{obj.id}:delete',
        }.get(action)


def get_task_minion_service(
    repo: Annotated[TaskMinionRepository, Depends(get_task_minion_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> TaskMinionService:
    return TaskMinionService(
        repo=repo,
        rdb=rdb,
    )
