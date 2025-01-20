from typing import Annotated

from beanie import PydanticObjectId
from fastapi import Depends
from pydantic import BaseModel

from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.tasks.crud import task_crud
from fastms_core.tasks.exceptions import TaskDoesNotExistException
from fastms_core.tasks.models import Task
from fastms_core.tasks.schemas import TaskCreateSchema


class TaskService:
    async def create_obj(self, obj_data: TaskCreateSchema) -> Task:
        task = await task_crud.create(obj_in=obj_data)

        return task

    async def get_obj(self, obj_id: PydanticObjectId) -> Task:
        task: Task = await task_crud.get(obj_id)

        if task:
            return task

        msg = 'Task does not found'
        raise TaskDoesNotExistException(msg)

    async def get_list(
            self, query: dict | None = None, projection_model: type[BaseModel] = Task
    ) -> list[type[BaseModel]]:
        tasks = await task_crud.get_multi(search=query, projection_model=projection_model)

        return tasks

    async def get_list_paginated(
            self, page, per_page, query: dict | None = None, projection_model: type[BaseModel] = Task
    ) -> PaginatedResponse[type[BaseModel]]:
        tasks = await task_crud.get_paginated(
            page=page, per_page=per_page, search=query, projection_model=projection_model
        )

        return tasks


async def get_task_service():
    task_service = TaskService()
    yield task_service


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
