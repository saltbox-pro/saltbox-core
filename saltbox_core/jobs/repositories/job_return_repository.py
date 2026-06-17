import json
from collections.abc import Callable
from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnModel
from saltbox_sdk.db.mongo.aggregations import AddFieldsAggregationStage, AggregatedField, AggregationsStore
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, ProjectionModel
from saltbox_sdk.db.redis.config import get_redis


class JobReturnRepository(BaseMongoRepository[JobReturnModel]):
    class Meta:
        collection_name = 'job_returns'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'job_return_jid_index_asc': [('jid', pymongo.ASCENDING)],
            'job_return_jid_salt_master_index_asc': [('jid', pymongo.ASCENDING), ('salt_master', pymongo.ASCENDING)],
            'jid__salt_master__status_index_asc': [
                ('jid', pymongo.ASCENDING),
                ('salt_master', pymongo.ASCENDING),
                ('status', pymongo.ASCENDING),
            ],
            'job_return_jid_minion_id_index_asc': [('jid', pymongo.ASCENDING), ('minion_id', pymongo.ASCENDING)],
            'job_return_unique_index_asc': [
                ('jid', pymongo.ASCENDING),
                ('salt_master', pymongo.ASCENDING),
                ('minion_id', pymongo.ASCENDING),
            ],
            'source_asc': [('source.type', pymongo.ASCENDING), ('source.id', pymongo.ASCENDING)],
            'source_with_tgt_asc': [
                ('source.type', pymongo.ASCENDING),
                ('source.id', pymongo.ASCENDING),
                ('salt_master', pymongo.ASCENDING),
                ('minion_id', pymongo.ASCENDING),
            ],
        }
        aggregations: ClassVar[AggregationsStore] = AggregationsStore(
            aggregations=[
                AggregatedField(
                    field_name='success',
                    stages=[
                        AddFieldsAggregationStage(
                            fields={
                                'success': {
                                    '$cond': {
                                        'if': {'$eq': ['$retcode', None]},
                                        'then': None,
                                        'else': {'$eq': ['$retcode', 0]},
                                    }
                                }
                            }
                        )
                    ],
                ),
            ]
        )

    def __init__(self, database: AsyncDatabase, rdb: Redis):
        self.rdb: Redis = rdb
        super().__init__(database=database)

    async def prepare_object_data(
        self, data: dict[str, Any], projection_model: type[ProjectionModel] | None = None
    ) -> dict[str, Any]:
        data = await super().prepare_object_data(data=data, projection_model=projection_model)
        projection_model_class = projection_model if projection_model is not None else JobReturnModel

        if 'data' in projection_model_class.model_fields:
            return_data: Any = None

            try:
                raw_return: str | bytes | None = await self.rdb.hget(
                    name=f'master:{data["salt_master"]}:job:{data["jid"]}:return-data', key=data['minion_id']
                )

                if raw_return:
                    return_data = json.loads(raw_return)
            except Exception as e:
                logger.info(f'Failed to retrieve job return data: {e}')

            data['data'] = return_data

        return data

    @staticmethod
    def format_data(data: Any) -> list[dict]:
        def _format_dict(_data: dict) -> list[dict]:
            res: list[dict] = []

            try:
                for key, value in _data.items():
                    res.append({'key': key, **value})
            except TypeError:
                for key, value in _data.items():
                    res.append({'key': key, 'value': value})

            return res

        def _format_list(_data: list[Any]) -> list[dict]:
            res: list[dict] = []

            for item in _data:
                if isinstance(item, dict):
                    res.append(item)
                else:
                    res.append({'value': item})

            return res

        def _format_default(_data: Any) -> list[dict]:
            return [{'value': _data}]

        format_callbacks_map: dict[type, Callable[[Any], list[dict]]] = {
            dict: _format_dict,
            list: _format_list,
        }

        return format_callbacks_map.get(type(data), _format_default)(data)


def get_job_return_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
    rdb: Annotated[Redis, Depends(get_redis)],
) -> JobReturnRepository:
    return JobReturnRepository(database=db, rdb=rdb)
