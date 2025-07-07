import json
import logging.config
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated, Any, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import Field, NonNegativeInt, PastDatetime
from pydantic import ValidationError as PydanticValidationError
from redis import exceptions as redis_exceptions

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.redis.config import RedisDependency
from salt_box_core.db.redis.repository_sortedset_base import ProjectionModel
from salt_box_core.db.schemas_base import CursoredResponse, PaginatedResponse
from salt_box_core.event_bus.masters_bus import send_message_to_master
from salt_box_core.jobs.exceptions import (
    JobCreateException,
    JobDoesNotExistsException,
    JobMultipleReturnsException,
    JobServiceException,
    JobServiceInvalidArgsException,
)
from salt_box_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from salt_box_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel, JobResult, JobUpdateSchema
from salt_box_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from salt_box_core.masters.schemas.master_schemas import MasterModel
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from salt_box_core.utilities.jid import JID, JidError
from salt_box_core.utilities.serivces.redis_sortedset_base_service import RedisSortedsetBaseService
from saltbox_bridge_messages import CoreNewJobAsyncRequest, MasterStatus

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)

JOB_CREATE_HASH_NAME: str = 'job_create:{jid}'


class JobService(RedisSortedsetBaseService[JobRepository, JobModel, JobCreateSchema, JobUpdateSchema]):
    def __init__(
        self,
        rdb: RedisDependency,
        job_repository: JobRepository,
        job_schema_service: JobSchemaService,
        master_service: MasterService,
    ):
        self.rdb = rdb
        self.job_schema_service = job_schema_service
        self.master_service = master_service
        super().__init__(job_repository)

    @overload
    async def create(self, data: JobCreateSchema) -> JobModel: ...

    @overload
    async def create(self, data: JobCreateSchema, projection_model: type[ProjectionModel]) -> ProjectionModel: ...

    async def create(
        self, data: JobCreateSchema, projection_model: type[ProjectionModel] | None = None
    ) -> JobModel | ProjectionModel:
        if not data.jid:
            jid = str(JID.generate())
        else:
            jid = data.jid

        create_job_hash_name: str = JOB_CREATE_HASH_NAME.format(jid=jid)

        try:
            validated_data: dict = await self.job_schema_service.get_validated_data(
                name=data.fun,
                data=data.data.model_dump(exclude_none=True, by_alias=True) if data.data else {},
            )
        except JsonSchemaValidationError as err:
            raise JobCreateException(err) from err

        try:
            master: MasterModel = await self.master_service.get_by_master_id(data.salt_master)
        except ObjectNotFoundError as e:
            raise JobCreateException(str(e)) from e

        if master.status != MasterStatus.ACCEPTED:
            err_msg = 'Master is not accepted'
            raise JobCreateException(err_msg)

        try:
            _data: dict[str, str] = {
                'jid': f'{jid}-{data.jid_postfix}' if data.jid_postfix else jid,
                'fun': data.fun,
                'tgt': data.tgt,
                'tgt_type': data.tgt_type,
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

            msg = CoreNewJobAsyncRequest(hash_name=create_job_hash_name, master=master.master_id)
            await send_message_to_master(message=msg, message_tag='run_job')
        except redis_exceptions.RedisError as error:
            raise JobCreateException(error) from error

        if projection_model:
            return await self.get_job(jid=JID(jid), projection_model=projection_model)
        else:
            return await self.get_job(jid=JID(jid))

    async def stop_job(self, jid: JID) -> None: ...  # TODO (i.moshkov): stop jobs

    async def _get_job_data_from_store(self, jid: JID) -> dict[str, Any] | None:
        ts = jid.to_timestamp()
        job_data = await self.rdb.zrange('jobs', start=ts, end=ts, byscore=True)  # type: ignore[call-overload]

        if job_data:
            if len(job_data) > 1:
                msg = f'Multiple jobs for JID {jid}'
                raise JobMultipleReturnsException(msg)

            res: dict[str, Any] = json.loads(job_data[0])
            res['status'] = JobModel.JobStatus.started

            return res

        return None

    async def _get_job_data_from_queue(self, job_hash_name: str) -> dict[str, Any] | None:
        job_data: dict[bytes, bytes] = await self.rdb.hgetall(job_hash_name)

        if job_data:
            return {
                'jid': job_data[b'jid'].decode()[:20],
                'tgt': job_data[b'tgt'].decode(),
                'tgt_type': job_data[b'tgt_type'].decode(),
                'fun': job_data[b'fun'].decode(),
                'arg': json.loads(job_data[b'arg']) if b'arg' in job_data else None,
                'kwarg': json.loads(job_data[b'kwarg']) if b'kwarg' in job_data else None,
                'status': JobModel.JobStatus.in_queue,
            }
        return None

    async def get_job(
        self, jid: JID, projection_model: type[ProjectionModel] | None = None
    ) -> JobModel | ProjectionModel:
        job_data = await self._get_job_data_from_store(jid)

        if not job_data:
            job_data = await self._get_job_data_from_queue(JOB_CREATE_HASH_NAME.format(jid=str(jid)))

        if not job_data:
            msg = 'Job not found'
            raise JobDoesNotExistsException(msg)

        if projection_model:
            return projection_model(**job_data)
        else:
            return JobModel(**job_data)

    @staticmethod
    def __get_start_end_from_dt(
        start_datetime: Annotated[datetime, PastDatetime], end_datetime: datetime
    ) -> tuple[float, float]:
        try:
            start = JID.from_datetime(start_datetime).to_timestamp()
            end = JID.from_datetime(end_datetime).to_timestamp()
        except JidError as err:
            msg = f'Invalid range: {err}'
            raise JobServiceInvalidArgsException(msg) from err

        return start, end

    @overload
    async def get_list_cursored_by_dt(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        cursor: int,
        count: int,
        match: str | None,
    ) -> CursoredResponse[JobModel]: ...

    @overload
    async def get_list_cursored_by_dt(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        cursor: int,
        count: int,
        match: str | None,
        projection_model: type[ProjectionModel],
    ) -> CursoredResponse[ProjectionModel]: ...

    async def get_list_cursored_by_dt(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        cursor: int = 0,
        count: int = 100,
        match: str | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> CursoredResponse[JobModel] | CursoredResponse[ProjectionModel]:
        start, end = self.__get_start_end_from_dt(start_datetime, end_datetime)

        return await self.get_list_cursored(
            start=start, end=end, cursor=cursor, count=count, match=match, projection_model=projection_model
        )

    async def get_list_by_dt(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[JobModel] | list[ProjectionModel]:
        start, end = self.__get_start_end_from_dt(start_datetime, end_datetime)

        if projection_model:
            return await super().get_list(
                start=int(start), end=int(end), limit=limit, skip=skip, desc=desc, projection_model=projection_model
            )
        else:
            return await super().get_list(start=int(start), end=int(end), limit=limit, skip=skip, desc=desc)

    @overload
    async def get_list_by_dt_paginated(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
    ) -> PaginatedResponse[JobModel]: ...

    @overload
    async def get_list_by_dt_paginated(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
        *,
        projection_model: type[ProjectionModel],
    ) -> PaginatedResponse[ProjectionModel]: ...

    async def get_list_by_dt_paginated(
        self,
        start_datetime: Annotated[datetime, PastDatetime],
        end_datetime: datetime,
        limit: int | None = None,
        skip: int = 0,
        desc: bool = False,
        projection_model: type[ProjectionModel] | None = None,
    ) -> PaginatedResponse[JobModel] | PaginatedResponse[ProjectionModel]:
        start, end = self.__get_start_end_from_dt(start_datetime, end_datetime)

        if projection_model:
            return await super().get_list_paginated(
                start=int(start), end=int(end), limit=limit, skip=skip, desc=desc, projection_model=projection_model
            )
        else:
            return await super().get_list_paginated(start=int(start), end=int(end), limit=limit, skip=skip, desc=desc)

    async def delete_fake_jobs(self, label: str | None = None) -> int:
        cur = 0
        count = 1000  # FIXME (a.karmanov) : dangled value, deciede to move to args
        label_field = '_fake_message_label'  # FIXME
        key = 'jobs'
        deletions = 0

        if label is None:
            match = f'*"{label_field}": *'
        else:
            match = f'*"{label_field}": "{label}"*'
        logger.error(match)

        while True:
            try:
                cur, records = await self.rdb.zscan(name=key, cursor=cur, match=match, count=count,)
                logger.error(records)
                if records:
                    deletions += await self.rdb.zrem(key, *[i[0] for i in records])
            except redis_exceptions.ResponseError as exc:
                raise JobServiceException(str(exc)) from exc
            if cur == 0:
                return deletions

    async def get_job_returns(
        self,
        jid: JID,
        count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
        cursor: NonNegativeInt = 0,
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
            except PydanticValidationError as e:
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
            except PydanticValidationError as e:
                raise JobServiceException(e.errors()) from e

        return res

    async def get_job_returns_count(self, jid: JID) -> int:
        returns_count = await self.rdb.hlen(name=f'job:{jid}:return')

        if not returns_count:
            return 0

        return returns_count


async def get_job_service(
    rdb: RedisDependency,
    job_repository: Annotated[JobRepository, Depends(get_job_repository)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> AsyncGenerator[JobService, None]:
    job_service = JobService(
        rdb=rdb, job_repository=job_repository, job_schema_service=job_schema_service, master_service=master_service
    )
    yield job_service


JobServiceDependency = Annotated[JobService, Depends(get_job_service)]
