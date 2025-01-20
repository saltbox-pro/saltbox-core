from typing import Annotated

from beanie import PydanticObjectId
from fastapi import Depends
from pydantic import BaseModel

from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.db.redis import RedisDependency
from fastms_core.tasks.crud import task_template_crud
from fastms_core.tasks.exceptions import TaskTemplateDoesNotExistException
from fastms_core.tasks.models import TaskTemplate
from fastms_core.tasks.schemas import TaskCreateSchema


class TaskTemplateService:
    def __init__(self, rdb: RedisDependency):
        self.rdb = rdb

    async def create_obj(self, obj_data: TaskCreateSchema) -> TaskTemplate:
        task_template = await task_template_crud.create(obj_in=obj_data)

        return task_template

    async def get_obj(self, obj_id: PydanticObjectId) -> TaskTemplate:
        task_template: TaskTemplate = await task_template_crud.get(obj_id)

        if task_template:
            return task_template

        msg = 'Task template does not found'
        raise TaskTemplateDoesNotExistException(msg)

    async def get_list(
            self, query: dict | None = None, projection_model: type[BaseModel] = TaskTemplate
    ) -> list[type[BaseModel]]:
        task_templates = await task_template_crud.get_multi(search=query, projection_model=projection_model)

        return task_templates

    async def get_list_paginated(
            self, page, per_page, query: dict | None = None, projection_model: type[BaseModel] = TaskTemplate
    ) -> PaginatedResponse[type[BaseModel]]:
        task_templates = await task_template_crud.get_paginated(
            page=page, per_page=per_page, search=query, projection_model=projection_model
        )

        return task_templates

    async def update_obj(self, obj_id: PydanticObjectId, obj_data: TaskCreateSchema) -> TaskTemplate:
        obj = await task_template_crud.get(id=obj_id)

        if not obj:
            msg = 'Task template does not found'
            raise TaskTemplateDoesNotExistException(msg)

        updated_obj = await task_template_crud.update(db_obj=obj, obj_in=obj_data)

        return updated_obj

    async def delete_obj(self, obj_id: PydanticObjectId):
        obj = await task_template_crud.get(id=obj_id)

        if not obj:
            msg = 'Task template does not found'
            raise TaskTemplateDoesNotExistException(msg)

        await task_template_crud.remove(id=obj_id)


async def get_task_template_service(rdb: RedisDependency):
    task_template_service = TaskTemplateService(rdb=rdb)
    yield task_template_service


TaskTemplateServiceDependency = Annotated[TaskTemplateService, Depends(get_task_template_service)]
