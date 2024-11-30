import logging.config

from fastapi.encoders import jsonable_encoder

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.crud_base import CRUDBase
from fastms_core.tasks.models import Task, TaskTemplate
from fastms_core.tasks.schemas import (
    TaskCreateSchema,
    TaskListSchema,
    TaskTemplateCreateSchema,
    TaskTemplateListSchema,
    TaskTemplateUpdateSchema,
    TaskUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CRUDTask(CRUDBase[Task, TaskListSchema, TaskCreateSchema, TaskUpdateSchema]):
    async def create(self, *, obj_in: TaskCreateSchema) -> Task:
        task_raw_data = jsonable_encoder(obj_in)

        task_template = await TaskTemplate.get(task_raw_data['task_template_id'])

        if not task_template:
            msg = 'Task template not found'
            raise ValueError(msg)

        return await task_template.create_task(
            variables_data=task_raw_data['variables_data'],
            tgt_type=task_raw_data['tgt_type'],
            tgt_value=task_raw_data['tgt_value'],
            batch_size=task_raw_data['batch_size'],
            max_retries=task_raw_data['max_retries'],
        )


class CRUDTaskTemplate(
    CRUDBase[TaskTemplate, TaskTemplateListSchema, TaskTemplateCreateSchema, TaskTemplateUpdateSchema]
):
    pass


task_crud = CRUDTask(Task)
task_template_crud = CRUDTaskTemplate(TaskTemplate)
