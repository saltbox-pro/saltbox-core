from datetime import UTC, datetime
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.db.redis import RedisDependency
from fastms_core.tasks.crud import task_crud
from fastms_core.tasks.exceptions import TaskDoesNotExistException
from fastms_core.tasks.models import Task
from fastms_core.tasks.schemas import TaskCreateSchema, TaskUpdateSchema


class TaskService:
    def __init__(self, rdb: Redis):
        self.rdb = rdb

    async def create_obj(self, obj_data: TaskCreateSchema, notify: bool = True) -> Task:
        task = await task_crud.create(obj_in=obj_data)

        if notify:
            await self.rdb.publish(channel=f'task:{task.id}:create', message=task.model_dump_json(by_alias=True))

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

    async def update_obj(self, obj_id: PydanticObjectId, obj_data: TaskUpdateSchema, notify: bool = True) -> Task:
        obj = await task_crud.get(id=obj_id)

        if not obj:
            msg = 'Task does not found'
            raise TaskDoesNotExistException(msg)

        if obj.status != obj_data.status:
            stamp_field_name = {
                Task.TaskStatus.running: 'run_stamp',
                Task.TaskStatus.stopped: 'stopped_stamp',
                Task.TaskStatus.finished: 'finished_stamp',
            }.get(obj_data.status)

            if stamp_field_name:
                obj_data.__setattr__(stamp_field_name, str(datetime.now(UTC).timestamp()))

        updated_obj = await task_crud.update(db_obj=obj, obj_in=obj_data)

        if notify:
            await self.rdb.publish(
                channel=f'task:{updated_obj.id}:update',
                message=updated_obj.model_dump_json(by_alias=True)
            )

        return updated_obj

    async def delete_obj(self, obj_id: PydanticObjectId, notify: bool = True):
        obj = await task_crud.get(id=obj_id)

        if not obj:
            msg = 'Task template does not found'
            raise TaskDoesNotExistException(msg)

        await task_crud.remove(id=obj_id)

        if notify:
            await self.rdb.publish(
                channel=f'task:{obj.id}:delete',
                message=obj.model_dump_json(by_alias=True)
            )


async def get_task_service(rdb: RedisDependency):
    task_service = TaskService(rdb=rdb)
    yield task_service


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
