import json
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel
from redis.asyncio import Redis

from fastms_core.db.exceptions import ObjectNotFoundError
from fastms_core.db.mongo.schemas_base import PyObjectId
from fastms_core.db.redis import RedisDependency
from fastms_core.db.repository_base import ProjectionSchemaType
from fastms_core.tasks.repository import TaskRepository
from fastms_core.tasks.schemas import (
    TaskCreateFromTemplateSchema,
    TaskCreateSchema,
    TaskListSchema,
    TaskSchema,
    TaskTemplateSchema,
    TaskUpdateSchema,
)
from fastms_core.tasks.services.tasks_templates import TaskTemplateService, TaskTemplateServiceDependency
from fastms_core.utilities.exceptions import ObjectDoesNotExistError
from fastms_core.utilities.helpers import get_now_stamp_str
from fastms_core.utilities.service_base import BaseService


class TaskService(
    BaseService[
        TaskRepository,
        TaskSchema,
        TaskListSchema,
        TaskCreateSchema,
        TaskUpdateSchema
    ]
):
    repository_class = TaskRepository

    def __init__(self, rdb: Redis, task_template_service: TaskTemplateService):
        self.task_template_service = task_template_service
        self.rdb = rdb

        super().__init__()

    async def create_obj(self, obj_data: TaskCreateFromTemplateSchema, notify: bool = True) -> TaskSchema:
        task_template: TaskTemplateSchema = await self.task_template_service.get_obj(
            obj_id=obj_data.task_template_id,
            projection_schema=TaskTemplateSchema
        )

        context: dict = self.task_template_service.get_context(
            task_template=task_template, variables_data=obj_data.variables_data
        )
        task_args = self.task_template_service.get_task_args(task_template, obj_data.variables_data, context)
        task_kwargs = self.task_template_service.get_task_kwargs(task_template, obj_data.variables_data, context)

        task: TaskSchema = await self.repository.create(obj=TaskCreateSchema(**{
            'task_template_id': task_template.id,
            'fun': task_template.fun,
            'task_args': task_args,
            'task_kwargs': task_kwargs,
            'tgt_type': obj_data.tgt_type,
            'tgt_value': obj_data.tgt_value,
            'batch_size': obj_data.batch_size,
            'max_retries': obj_data.max_retries,
        }))

        if notify:
            await self.rdb.publish(channel=f'task:{task.id}:create', message=self.__prepare_pub_message(task))

        return task

    async def update_obj(
            self,
            obj_id: PyObjectId,
            obj_data: TaskUpdateSchema,
            projection_schema: type[ProjectionSchemaType] = ProjectionSchemaType,
            notify: bool = True,
    ) -> TaskSchema:
        try:
            obj = await self.get_obj(obj_id=obj_id, projection_schema=TaskSchema)

            if obj.status != obj_data.status:
                stamp_field_name = {
                    TaskSchema.TaskStatus.running: 'run_stamp',
                    TaskSchema.TaskStatus.stopped: 'stopped_stamp',
                    TaskSchema.TaskStatus.finished: 'finished_stamp',
                }.get(obj_data.status)

                if stamp_field_name:
                    obj_data.__setattr__(stamp_field_name, get_now_stamp_str())

            updated_obj = await self.repository.update(query=obj_id, obj=obj_data, projection_schema=projection_schema)
        except ObjectNotFoundError as e:
            msg = 'Object does not found'
            raise ObjectDoesNotExistError(msg) from e

        if notify:
            await self.rdb.publish(
                channel=f'task:{updated_obj.id}:update',
                message=self.__prepare_pub_message(updated_obj)
            )

        return updated_obj

    async def delete_obj(self, obj_id: PyObjectId, notify: bool = True):
        obj = await self.get_obj(obj_id=obj_id, projection_schema=TaskSchema)
        deleted_count: int = await super().delete_obj(obj_id=obj_id)

        if notify:
            await self.rdb.publish(
                channel=f'task:{obj.id}:delete',
                message=self.__prepare_pub_message(obj)
            )

        return deleted_count

    def __prepare_pub_message(self, obj: BaseModel) -> str:
        data: dict = obj.model_dump(by_alias=True, mode='json')

        if 'id' in data:
            data['_id'] = data['id']

        return json.dumps(data)


async def get_task_service(rdb: RedisDependency, task_template_service: TaskTemplateServiceDependency):
    task_service = TaskService(rdb=rdb, task_template_service=task_template_service)
    yield task_service


TaskServiceDependency = Annotated[TaskService, Depends(get_task_service)]
