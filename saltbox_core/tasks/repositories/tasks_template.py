from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import SETTINGS
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
                        UnwindAggregationStage(path='$repo_info', preserve_null_and_empty_arrays=True),
                    ],
                )
            ]
        )
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_repo_id_unique_index': [
                ('name', pymongo.ASCENDING),
                ('repo_id', pymongo.ASCENDING),
            ]
        }

    async def prepare_object_data(
        self,
        data: dict[str, Any],
        projection_model: type[ProjectionModel] | None = None,
    ) -> dict[str, Any]:
        data = await super().prepare_object_data(data=data, projection_model=projection_model)
        projection_model_class = projection_model if projection_model is not None else TaskTemplateModel

        if 'defaults' in projection_model_class.model_fields:
            template_defaults = data.get('defaults', {}) or {}

            data['defaults'] = {}
            data['defaults']['batch_size'] = template_defaults.get('batch_size', SETTINGS.tasks_defaults_batch_size)
            data['defaults']['max_jobs_count_at_same_time'] = template_defaults.get(
                'max_jobs_count_at_same_time', SETTINGS.tasks_defaults_max_jobs_count_at_same_time
            )
            data['defaults']['max_retries'] = template_defaults.get('max_retries', SETTINGS.tasks_defaults_max_retries)
            data['defaults']['retry_delay'] = template_defaults.get('retry_delay', SETTINGS.tasks_defaults_retry_delay)

        return data


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
