import datetime
import json
import logging.config
from collections.abc import AsyncGenerator
from typing import Annotated

import pydantic
from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from redis import exceptions as redis_exceptions

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.redis import RedisDependency
from salt_box_core.jobs.exceptions import (
    JobCreateException,
    JobDoesNotExistsException,
    JobMultipleReturnsException,
    JobServiceException,
    JobServiceInvalidArgsException,
)
from salt_box_core.jobs.schemas import Job, JobCreate, JobResult
from salt_box_core.schema_sync.services.schema_service import JSONSchemaService, get_json_schema_service
from salt_box_core.utilities.jid import JID, JidError

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

JOB_CREATE_HASH_NAME: str = 'job_create:{jid}'


class JobService:
    def __init__(self, rdb: RedisDependency, json_schema_service: JSONSchemaService):
        self.rdb = rdb
        self.json_schema_service = json_schema_service

    async def create_job(self, job_data: JobCreate) -> JID:
        if not job_data.jid:
            jid = str(JID.generate())
        else:
            jid = job_data.jid

        create_job_hash_name: str = JOB_CREATE_HASH_NAME.format(jid=jid)

        try:
            validated_data: dict = await self.json_schema_service.get_validated_data(
                name=job_data.fun,
                data=job_data.data.model_dump(exclude_none=True, by_alias=True) if job_data.data else {},
            )
        except JsonSchemaValidationError as err:
            raise JobCreateException(err) from err

        try:
            _data: dict[str, str] = {
                'jid': f'{jid}-{job_data.jid_postfix}' if job_data.jid_postfix else jid,
                'fun': job_data.fun,
                'tgt': job_data.tgt,
                'tgt_type': job_data.tgt_type,
            }

            if 'args' in validated_data:
                _data['arg'] = json.dumps(validated_data['args'])
            if 'kwargs' in validated_data:
                _data['kwarg'] = json.dumps(validated_data['kwargs'])

            await self.rdb.hmset(
                name=create_job_hash_name,
                # TODO (i.moshkov): check and fix later
                mapping=_data,  # type: ignore[arg-type]
            )
            await self.rdb.expire(name=create_job_hash_name, time=60 * 10)

            await self.rdb.publish(
                channel='salt-service',
                message=json.dumps(
                    {
                        'command': f'job/run/{job_data.salt_master}' if job_data.salt_master else 'job/run',
                        'payload': {
                            'hash_name': create_job_hash_name,
                        },
                    }
                ),
            )
        except redis_exceptions.RedisError as error:
            raise JobCreateException(error) from error

        return JID(jid)

    async def _get_job_from_store(self, jid: JID) -> Job | None:
        ts = jid.to_timestamp()
        job_data = await self.rdb.zrange('jobs', start=ts, end=ts, byscore=True)  # type: ignore[call-overload]

        if job_data:
            if len(job_data) > 1:
                msg = f'Multiple jobs for JID {jid}'
                raise JobMultipleReturnsException(msg)

            res = json.loads(job_data[0])
            res['status'] = Job.JobStatus.started

            return Job(**res)
        return None

    async def _get_job_data_from_queue(self, job_hash_name: str) -> Job | None:
        job_data: dict[bytes, bytes] = await self.rdb.hgetall(job_hash_name)

        if job_data:
            return Job(
                **{
                    'jid': job_data[b'jid'].decode()[:20],
                    'tgt': job_data[b'tgt'].decode(),
                    'tgt_type': job_data[b'tgt_type'].decode(),
                    'fun': job_data[b'fun'].decode(),
                    'arg': json.loads(job_data[b'arg']) if b'arg' in job_data else None,
                    'kwarg': json.loads(job_data[b'kwarg']) if b'kwarg' in job_data else None,
                    'status': Job.JobStatus.in_queue,
                }
            )
        return None

    async def get_job(self, jid: JID) -> Job:
        job = await self._get_job_from_store(jid)

        if not job:
            job = await self._get_job_data_from_queue(JOB_CREATE_HASH_NAME.format(jid=str(jid)))

        if not job:
            msg = 'Job not found'
            raise JobDoesNotExistsException(msg)

        return job

    async def get_jobs(
        self, start_datetime: pydantic.PastDatetime, end_datetime: datetime.datetime | None = None
    ) -> list[Job]:
        if end_datetime is None:
            end_datetime = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)

        try:
            start = JID.from_datetime(start_datetime).to_timestamp()
            end = JID.from_datetime(end_datetime).to_timestamp()
        except JidError as err:
            msg = f'Invalid range: {err}'
            raise JobServiceInvalidArgsException(msg) from err

        res_ = await self.rdb.zrange('jobs', start=end, end=start, desc=True, byscore=True)  # type: ignore[call-overload]
        res = [{'status': Job.JobStatus.started, **json.loads(i)} for i in res_]

        return [Job(**i) for i in res]

    async def get_job_returns(
        self,
        jid: JID,
        count: Annotated[int, pydantic.Field(gt=0, lt=SETTINGS.max_count)] = 10,
        cursor: pydantic.NonNegativeInt = 0,
    ) -> tuple[list[JobResult], int]:
        try:
            next_cur, records = await self.rdb.hscan(name=f'job:{jid}:return', cursor=cursor, count=count)
        except redis_exceptions.ResponseError as exc:
            raise JobServiceException(str(exc)) from exc

        res = []
        for _, ret in records.items():
            data = json.loads(ret)

            try:
                res.append(JobResult(**data))
            except pydantic.ValidationError as e:
                raise JobServiceException(e.errors()) from e

        return res, next_cur

    async def get_job_all_returns(self, jid: JID) -> list[JobResult]:
        try:
            records = await self.rdb.hgetall(name=f'job:{jid}:return')
        except redis_exceptions.ResponseError as exc:
            raise JobServiceException(str(exc)) from exc

        res: list[JobResult] = []
        for _, ret in records.items():
            data = json.loads(ret)

            try:
                res.append(JobResult(**data))
            except pydantic.ValidationError as e:
                raise JobServiceException(e.errors()) from e

        return res

    async def get_job_returns_count(self, jid: JID) -> int:
        returns_count = await self.rdb.hlen(name=f'job:{jid}:return')

        if not returns_count:
            return 0

        return returns_count

    async def is_job_exists(self, jid: JID) -> bool:
        try:
            job = await self.get_job(jid)

            return True if job else False
        except JobDoesNotExistsException:
            return False


async def get_job_service(
    rdb: RedisDependency, json_schema_service: Annotated[JSONSchemaService, Depends(get_json_schema_service)]
) -> AsyncGenerator[JobService, None]:
    job_service = JobService(rdb=rdb, json_schema_service=json_schema_service)
    yield job_service


JobServiceDependency = Annotated[JobService, Depends(get_job_service)]
