from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from salt_box_core.db.redis.config import get_redis
from salt_box_core.db.redis.repository_sortedset_base import SortedsetRedisRepository
from salt_box_core.jobs.schemas.job_schemas import JobModel


class JobRepository(SortedsetRedisRepository[JobModel]):
    class Meta:
        collection_name = 'jobs'
        id_field_name = 'jid'


def get_job_repository(db: Annotated[Redis, Depends(get_redis)]) -> JobRepository:
    return JobRepository(db)
