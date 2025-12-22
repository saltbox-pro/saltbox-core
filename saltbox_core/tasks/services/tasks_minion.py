from typing import Annotated

from fastapi import Depends

from saltbox_core.tasks.repositories.tasks_minion import TaskMinionRepository, get_task_minion_repository
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema, TaskMinionModel, TaskMinionUpdateSchema
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class TaskMinionService(
    MongoBaseService[TaskMinionRepository, TaskMinionModel, TaskMinionCreateSchema, TaskMinionUpdateSchema]
): ...


def get_task_minion_service(
    repo: Annotated[TaskMinionRepository, Depends(get_task_minion_repository)],
) -> TaskMinionService:
    return TaskMinionService(repo)
