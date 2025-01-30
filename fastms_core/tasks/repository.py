from fastms_core.db.mongo.repository import MongoDBBaseRepository
from fastms_core.tasks.schemas import (
    TaskCreateSchema,
    TaskListSchema,
    TaskSchema,
    TaskTemplateCreateSchema,
    TaskTemplateListSchema,
    TaskTemplateSchema,
    TaskTemplateUpdateSchema,
    TaskUpdateSchema,
)


class TaskRepository(MongoDBBaseRepository[TaskSchema, TaskListSchema, TaskCreateSchema, TaskUpdateSchema]):
    collection_name = 'tasks'
    projection_schema = TaskSchema


class TaskTemplateRepository(
    MongoDBBaseRepository[
        TaskTemplateSchema, TaskTemplateListSchema, TaskTemplateCreateSchema, TaskTemplateUpdateSchema
    ]
):
    collection_name = 'task_templates'
    projection_schema = TaskTemplateSchema
