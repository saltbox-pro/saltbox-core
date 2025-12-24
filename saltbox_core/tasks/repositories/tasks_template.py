from typing import Annotated, ClassVar, TypeVar

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.tasks_template import TaskTemplateModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.utils import AggregatedField, AggregationsStore

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskTemplateRepository(BaseMongoRepository[TaskTemplateModel]):
    class Meta:
        collection_name = 'task_templates'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='repo_info',
                    stages=[
                        {
                            '$lookup': {
                                'from': 'settings_sls_repos',
                                'localField': 'repo_id',
                                'foreignField': '_id',
                                'as': 'repo_info',
                                'pipeline': [{'$project': {'repo_url': 1, 'name': 1}}],
                            }
                        },
                        {'$unwind': '$repo_info'},
                    ],
                )
            ]
        )


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
