import logging.config

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
    pass


class CRUDTaskTemplate(
    CRUDBase[TaskTemplate, TaskTemplateListSchema, TaskTemplateCreateSchema, TaskTemplateUpdateSchema]
):
    pass


task_crud = CRUDTask(Task)
task_template_crud = CRUDTaskTemplate(TaskTemplate)
