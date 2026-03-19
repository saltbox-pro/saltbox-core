from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class JobRepository(BaseMongoRepository[JobModel]):
    class Meta:
        collection_name = 'jobs'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'job_jid_index_asc': [('jid', pymongo.ASCENDING)],
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='waiting_expires_at_dt',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'waiting_expires_at_dt': {
                                    '$dateAdd': {'startDate': '$created', 'unit': 'second', 'amount': '$ttl'}
                                }
                            }
                        )
                    ],
                ),
                AggregatedField(
                    field_name='returns',
                    stages=[
                        LookupAggregationStage(
                            from_collection='job_returns',
                            let={'salt_master': '$salt_master', 'jid': '$jid'},
                            pipeline=[
                                {
                                    '$match': {
                                        '$expr': {
                                            '$and': [
                                                {'$eq': ['$jid', '$$jid']},
                                                {'$eq': ['$salt_master', '$$salt_master']},
                                            ]
                                        }
                                    }
                                }
                            ],
                            as_field='returns',
                        )
                    ],
                ),
                AggregatedField(
                    field_name='returning',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'returning': {
                                    '$arrayToObject': {
                                        '$map': {
                                            'input': '$returns',
                                            'as': 'res',
                                            'in': {
                                                'k': '$$res.minion_id',
                                                'v': {
                                                    '$cond': {
                                                        'if': {'$eq': ['$$res.retcode', None]},
                                                        'then': None,
                                                        'else': {'$eq': ['$$res.retcode', 0]},
                                                    }
                                                },
                                            },
                                        }
                                    }
                                }
                            }
                        )
                    ],
                    parent_aggregations=['returns'],
                ),
                AggregatedField(
                    field_name='has_failed_job_returns',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'has_failed_job_returns': {
                                    '$anyElementTrue': {
                                        '$map': {
                                            'input': '$returns',
                                            'as': 'res',
                                            'in': {
                                                '$cond': {
                                                    'if': {'$eq': ['$$res.retcode', None]},
                                                    'then': False,
                                                    'else': {'$ne': ['$$res.retcode', 0]},
                                                }
                                            },
                                        }
                                    }
                                }
                            }
                        )
                    ],
                    parent_aggregations=['returns'],
                ),
            ]
        )


def get_job_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobRepository:
    return JobRepository(db)
