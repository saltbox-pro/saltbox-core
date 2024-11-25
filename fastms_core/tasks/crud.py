import logging.config

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.crud_base import CRUDBase
from fastms_core.tasks.models import TargetTemplate, TaskTemplate
from fastms_core.tasks.schemas import (
    TargetTemplateCreateSchema,
    TargetTemplateListSchema,
    TargetTemplateUpdateSchema,
    TaskTemplateCreateSchema,
    TaskTemplateListSchema,
    TaskTemplateUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CRUDTask(CRUDBase[TaskTemplate, TaskTemplateListSchema, TaskTemplateCreateSchema, TaskTemplateUpdateSchema]):
    pass


class CRUDTarget(
    CRUDBase[TargetTemplate, TargetTemplateListSchema, TargetTemplateCreateSchema, TargetTemplateUpdateSchema]
):
    pass


tasks_crud = CRUDTask(TaskTemplate)
targets_crud = CRUDTarget(TargetTemplate)
