from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.db.redis.repository_sortedset_base import SortedsetRedisRepository
from saltbox_sdk.db.redis.schemas_base import SortedSetId


class JobRepository(SortedsetRedisRepository[JobModel]):
    class Meta:
        collection_name = 'jobs'
        id_field_name = 'jid'

    @classmethod
    def _generate_id(cls, data: JobModel | dict[str, Any]) -> SortedSetId:
        logger.debug('!!!!_generate_id!!!!')
        jid = None

        if isinstance(data, dict):
            if 'jid' not in data:
                jid = JID.generate()
            else:
                jid = JID(data['jid'])
        elif isinstance(data, JobModel):
            jid = JID(data.jid)

        return jid.to_timestamp()


def get_job_repository(db: Annotated[Redis, Depends(get_redis)]) -> JobRepository:
    return JobRepository(db)
