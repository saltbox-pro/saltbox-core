from typing import Annotated, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.tasks.schemas.tasks_template import TaskTemplateModel
from saltbox_sdk.db.mongo.aggregations import (
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

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
                        LookupAggregationStage(
                            from_collection='settings_sls_repos',
                            local_field='repo_id',
                            foreign_field='_id',
                            as_field='repo_info',
                            pipeline=[{'$project': {'repo_url': 1, 'name': 1}}],
                        ),
                        UnwindAggregationStage(path='$repo_info'),
                    ],
                )
            ]
        )
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_repo_id_unique_index': [
                ('name', pymongo.ASCENDING),
                ('repo_id', pymongo.ASCENDING)
            ]
        }


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
