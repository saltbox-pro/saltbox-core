from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.task_templates.schemas.template import TaskTemplateModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ModelType = TypeVar('ModelType', bound=BaseModel)


class TaskTemplateRepository(BaseMongoRepository[TaskTemplateModel]):
    class Meta:
        collection_name = 'task_templates'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_unique_index': [('name', pymongo.ASCENDING)],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'name_unique_index': {'unique': True},
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='local_path',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_template_sources',
                            local_field='source_id',
                            foreign_field='_id',
                            as_field='_source',
                        ),
                        UnwindAggregationStage(path='$_source', preserve_null_and_empty_arrays=True),
                        AddFieldsAggregationStage(fields={'local_path': '$_source.local_path'}),
                    ],
                ),
                AggregatedField(
                    field_name='source_root',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_template_sources',
                            local_field='source_id',
                            foreign_field='_id',
                            as_field='_source',
                        ),
                        UnwindAggregationStage(path='$_source', preserve_null_and_empty_arrays=True),
                        AddFieldsAggregationStage(fields={'source_root': '$_source.root'}),
                    ],
                ),
            ]
        )


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
