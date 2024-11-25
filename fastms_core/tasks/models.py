from beanie import Document

from fastms_core.tasks.schemas import TargetTemplateSchema, TaskTemplateSchema


class TaskTemplate(Document, TaskTemplateSchema):
    class Settings:
        name = 'task_templates'


class TargetTemplate(Document, TargetTemplateSchema):
    class Settings:
        name = 'target_templates'
