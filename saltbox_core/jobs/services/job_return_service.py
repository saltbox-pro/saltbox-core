from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.client_session import (
    AsyncClientSession as MongoAsyncClientSession,
)
from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository, get_job_return_repository
from saltbox_core.jobs.schemas.job_return_schemas import (
    JobReturnCreateSchema,
    JobReturnDataListPaginatedResponse,
    JobReturnDataListSchema,
    JobReturnForDataList,
    JobReturnModel,
    JobReturnNotifySchema,
    JobReturnUpdateSchema,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService


class JobReturnService(
    MongoBaseWithNotifyService[JobReturnRepository, JobReturnModel, JobReturnCreateSchema, JobReturnUpdateSchema]
):
    async def get_data_list(
        self,
        query: Any,
        limit: int = 0,
        skip: int = 0,
        *,
        session: MongoAsyncClientSession | None = None,
        sort: dict[str, SortOrder] | None = None,
    ) -> JobReturnDataListSchema:
        data: list[dict[str, Any]] = []
        columns: list[str] = ['minion_id']
        job_reruns = await self.get_list(
            query=query,
            limit=limit,
            skip=skip,
            session=session,
            sort=sort,
            projection_model=JobReturnForDataList,
        )

        for job_rerun in job_reruns:
            list_of_job_return_formated_data = self.repo.format_data(job_rerun.data)

            for job_return_formated_data in list_of_job_return_formated_data:
                data.append({**job_return_formated_data, 'minion_id': job_rerun.minion_id})

                for column_name in job_return_formated_data.keys():
                    if column_name not in columns:
                        columns.append(column_name)

        return JobReturnDataListSchema(columns=list(columns), data=data)

    async def get_data_list_paginated(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        *,
        session: MongoAsyncClientSession | None = None,
        sort: dict[str, SortOrder] | None = None,
    ) -> JobReturnDataListPaginatedResponse:
        total = await self.count(query=query, session=session)
        data = await self.get_data_list(query=query, limit=limit, skip=skip, session=session, sort=sort)

        return JobReturnDataListPaginatedResponse.model_validate({'total': total, **data.model_dump()})

    @property
    def notify_taskiq_task(self) -> Callable:
        return send_notify_by_mongo_service

    @property
    def notify_schema(self) -> type[JobReturnNotifySchema]:
        return JobReturnNotifySchema

    @property
    def service_name(self) -> str:
        return 'job_return_service'

    def _get_notify_channel(self, obj: BaseModel, action: str) -> str | None:
        if not hasattr(obj, 'jid'):
            return None

        channels: dict[str, str] = {
            'create': f'job-return:{obj.jid}:create',
            'update': f'job-return:{obj.jid}:update',
            'delete': f'job-return:{obj.jid}:delete',
        }

        if (
            hasattr(obj, 'source')
            and obj.source
            and hasattr(obj.source, 'type')
            and hasattr(obj.source, 'id')
            and obj.source.type == 'task'
        ):
            channels.update(
                {
                    'create_task': f'task:{obj.source.id}:job-return:{obj.jid}:create',
                    'update_task': f'task:{obj.source.id}:job-return:{obj.jid}:update',
                    'delete_task': f'task:{obj.source.id}:job-return:{obj.jid}:delete',
                }
            )

        return channels.get(action)

    async def run_notify(self, obj_id: PyObjectId, action: str) -> None:
        try:
            obj = await self.get(query=obj_id, projection_model=self.notify_schema)

            channel = self._get_notify_channel(obj=obj, action=action)
            task_channel = self._get_notify_channel(obj=obj, action=f'{action}_task')

            async with self.rdb.pipeline() as pipe:
                if channel:
                    pipe.publish(channel=channel, message=self._prepare_pub_message(obj=obj))
                if task_channel:
                    pipe.publish(channel=task_channel, message=self._prepare_pub_message(obj=obj))

                await pipe.execute()
        except redis_exceptions.RedisError as e:
            logger.error(e)
        except ObjectNotFoundException:
            logger.debug(f'Object "{self.repo.Meta.collection_name}" for notifying not found by query: {obj_id}')


def get_job_return_service(
    rdb: Annotated[Redis, Depends(get_redis)],
    repo: Annotated[JobReturnRepository, Depends(get_job_return_repository)],
) -> JobReturnService:
    return JobReturnService(repo=repo, rdb=rdb)
