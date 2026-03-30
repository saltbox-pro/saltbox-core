from typing import Annotated, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnStatus
from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_sdk.db.mongo.aggregations import (
    AddFieldsAggregationStage,
    AggregatedField,
    AggregationsStore,
    LookupAggregationStage,
    UnwindAggregationStage,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


def get_count_by_status_lookup_aggregation_stage(status: JobReturnStatus | None = None) -> LookupAggregationStage:
    match_conditions = [{'$eq': ['$jid', '$$jid']}, {'$eq': ['$salt_master', '$$salt_master']}]

    if status is not None:
        match_conditions.append({'$eq': ['$status', status]})

    return LookupAggregationStage(
        from_collection='job_returns',
        let={'salt_master': '$salt_master', 'jid': '$jid'},
        pipeline=[{'$match': {'$expr': {'$and': match_conditions}}}, {'$count': 'count'}],
        as_field=f'minions_count.{status or "total"}',
    )


class JobRepository(BaseMongoRepository[JobModel]):
    class Meta:
        collection_name = 'jobs'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'job_jid_index_asc': [('jid', pymongo.ASCENDING)],
            'jid_and_salt_master_unique_index_asc': [('jid', pymongo.ASCENDING), ('salt_master', pymongo.ASCENDING)],
            'status_asc': [('status', pymongo.ASCENDING)],
            'created_asc': [('created', pymongo.ASCENDING)],
            'source_asc': [('source.type', pymongo.ASCENDING), ('source.id', pymongo.ASCENDING)],
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
                AggregatedField(
                    field_name='minions_count',
                    stages=[
                        get_count_by_status_lookup_aggregation_stage(),
                        get_count_by_status_lookup_aggregation_stage(JobReturnStatus.waiting),
                        get_count_by_status_lookup_aggregation_stage(JobReturnStatus.success),
                        get_count_by_status_lookup_aggregation_stage(JobReturnStatus.failed),
                        get_count_by_status_lookup_aggregation_stage(JobReturnStatus.timeout),
                        get_count_by_status_lookup_aggregation_stage(JobReturnStatus.ignored),
                        UnwindAggregationStage(path='$minions_count.total', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.waiting', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.success', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.failed', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.timeout', preserve_null_and_empty_arrays=True),
                        UnwindAggregationStage(path='$minions_count.ignored', preserve_null_and_empty_arrays=True),
                        AddFieldsAggregationStage(
                            fields={
                                'minions_count.total': {'$ifNull': ['$minions_count.total.count', 0]},
                                'minions_count.waiting': {'$ifNull': ['$minions_count.waiting.count', 0]},
                                'minions_count.success': {'$ifNull': ['$minions_count.success.count', 0]},
                                'minions_count.failed': {'$ifNull': ['$minions_count.failed.count', 0]},
                                'minions_count.timeout': {'$ifNull': ['$minions_count.timeout.count', 0]},
                                'minions_count.ignored': {'$ifNull': ['$minions_count.ignored.count', 0]},
                            }
                        ),
                    ],
                ),
            ]
        )


def get_job_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobRepository:
    return JobRepository(db)
