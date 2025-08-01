from typing import Annotated

from fastapi import Depends

from saltbox_core.tasks.repositories.task_template_repository import (
    TaskTemplateRepository,
    get_task_template_repository,
)
from saltbox_core.tasks.schemas.task_template_schemas import (
    TaskTemplateCreateSchema,
    TaskTemplateModel,
    TaskTemplateUpdateSchema,
)
from saltbox_core.utilities.json_schema import Draft4ValidatorWithDefaults
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class TaskTemplateService(
    MongoBaseService[TaskTemplateRepository, TaskTemplateModel, TaskTemplateCreateSchema, TaskTemplateUpdateSchema]
):
    async def get_by_name(self, name: str, sid: PyObjectId) -> TaskTemplateModel:
        return await self.repo.get({'name': name, 'repo_id': sid})

    async def get_validated_data(self, name: str, sid: PyObjectId, data: dict) -> dict:
        try:
            task_template = await self.get_by_name(name=name, sid=sid)
        except ObjectNotFoundException:
            task_template = await self.get_by_name('default', sid=sid)

        Draft4ValidatorWithDefaults(task_template.json_schema).validate(data)

        return data


async def get_task_template_service(
    repo: Annotated[TaskTemplateRepository, Depends(get_task_template_repository)],
) -> TaskTemplateService:
    return TaskTemplateService(repo)
