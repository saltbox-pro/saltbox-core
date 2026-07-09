from typing import Annotated, Any, ClassVar, TypeVar

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.task_templates.schemas.source import TemplateSourceModel
from saltbox_sdk.db.mongo.aggregations import (
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ModelType = TypeVar('ModelType', bound=BaseModel)


class TemplateSourceRepository(BaseMongoRepository[TemplateSourceModel]):
    class Meta:
        collection_name = 'task_template_sources'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'url_unique_index_asc': [('repo_url', pymongo.ASCENDING)],
            'name_unique_index': [('name', pymongo.ASCENDING)],
            'local_path_unique_index_asc': [('local_path', pymongo.ASCENDING)],
            'namespace_unique_index_asc': [('namespace', pymongo.ASCENDING)],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'url_unique_index_asc': {
                'unique': True,
                'partialFilterExpression': {'repo_url': {'$type': 'string'}},
            },
            'name_unique_index': {'unique': True},
            'local_path_unique_index_asc': {'unique': True},
            'namespace_unique_index_asc': {
                'unique': True,
                'partialFilterExpression': {'namespace': {'$type': 'string'}},
            },
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='templates',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_templates',
                            let={'source_id': '$_id'},
                            pipeline=[
                                {'$match': {'$expr': {'$eq': ['$source_id', '$$source_id']}}},
                                {
                                    '$project': {
                                        '_id': 1,
                                        'created': 1,
                                        'modified': 1,
                                        'source_id': 1,
                                        'title': 1,
                                        'description': 1,
                                        'fun': 1,
                                        'name': 1,
                                    }
                                },
                            ],
                            as_field='templates',
                        ),
                    ],
                ),
                AggregatedField(
                    field_name='files',
                    stages=[
                        LookupAggregationStage(
                            from_collection='task_template_files',
                            let={'source_id': '$_id'},
                            pipeline=[
                                {'$match': {'$expr': {'$eq': ['$source_id', '$$source_id']}}},
                                {
                                    '$project': {
                                        '_id': 1,
                                        'created': 1,
                                        'modified': 1,
                                        'source_id': 1,
                                        'file_type': 1,
                                        'rel_path': 1,
                                        'url': 1,
                                        'checksum': 1,
                                        'checksum_type': 1,
                                        'synced_on_sshfs': 1,
                                        'last_sync_error': 1,
                                    }
                                },
                            ],
                            as_field='files',
                        ),
                    ],
                ),
            ]
        )


def get_template_source_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TemplateSourceRepository:
    return TemplateSourceRepository(db)
