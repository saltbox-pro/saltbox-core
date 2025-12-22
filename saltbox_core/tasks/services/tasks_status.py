from typing import Annotated

from fastapi import Depends

from saltbox_core.tasks.repositories.tasks_status import TaskStatusRepository, get_task_status_repository
from saltbox_core.tasks.schemas.tasks_status import TaskStatusCreateSchema, TaskStatusModel, TaskStatusUpdateSchema
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class TaskStatusService(
    MongoBaseService[TaskStatusRepository, TaskStatusModel, TaskStatusCreateSchema, TaskStatusUpdateSchema]
): ...


def get_task_status_service(
    repo: Annotated[TaskStatusRepository, Depends(get_task_status_repository)],
) -> TaskStatusService:
    return TaskStatusService(repo)
