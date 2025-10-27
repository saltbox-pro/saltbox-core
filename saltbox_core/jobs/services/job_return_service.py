from typing import Annotated

from fastapi import Depends
from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_return_repository import JobReturnRepository, get_job_return_repository
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnCreateSchema, JobReturnModel, JobReturnUpdateSchema
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.serivces.mongo_base_service import ProjectionModel
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService


class JobReturnService(
    MongoBaseWithNotifyService[JobReturnRepository, JobReturnModel, JobReturnCreateSchema, JobReturnUpdateSchema]
):
    def _get_notify_channel(self, obj: JobReturnModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'jid'):
            return None

        channels: dict[str, str] = {
            'create': f'job-return:{obj.jid}:create',
            'update': f'job-return:{obj.jid}:update',
            'delete': f'job-return:{obj.jid}:delete',
        }

        if hasattr(obj, 'source') and obj.source:
            if obj.source.type == 'task':
                channels.update(
                    {
                        'create_task': f'task:{obj.source.id}:job-return:{obj.jid}:create',
                        'update_task': f'task:{obj.source.id}:job-return:{obj.jid}:update',
                        'delete_task': f'task:{obj.source.id}:job-return:{obj.jid}:delete',
                    }
                )

        return channels.get(action)

    async def _notify(self, obj: JobReturnModel | ProjectionModel, action: str) -> None:
        try:
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


def get_job_return_service(
    rdb: Annotated[Redis, Depends(get_redis)],
    repo: Annotated[JobReturnRepository, Depends(get_job_return_repository)],
) -> JobReturnService:
    return JobReturnService(repo=repo, rdb=rdb)
