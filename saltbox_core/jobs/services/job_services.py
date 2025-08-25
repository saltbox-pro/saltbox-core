import json
from datetime import datetime
from typing import Annotated, Any, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import Field, NonNegativeInt, PastDatetime
from pydantic import ValidationError as PydanticValidationError
from redis import exceptions as redis_exceptions

from saltbox_bridge_messages import CoreNewJobAsyncRequest, MasterStatus
from saltbox_core.config import SETTINGS
from saltbox_core.event_bus.redis.masters_bus import send_message_to_master
from saltbox_core.jobs.exceptions import (
    JobCreateException,
    JobDoesNotExistsException,
    JobMultipleReturnsException,
    JobServiceException,
    JobServiceInvalidArgsException,
)
from saltbox_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel, JobResult, JobUpdateSchema
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.masters.schemas.master_schemas import MasterModel
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.utilities.context import replace_raised
from saltbox_core.utilities.jid import JID, JidError
from saltbox_sdk.db.redis.repository_sortedset_base import ProjectionModel
from saltbox_sdk.db.schemas_base import CursoredResponse, PaginatedResponse
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.fastapi_utils.dependencies import RedisDependency
from saltbox_sdk.serivces.redis_sortedset_base_service import RedisSortedsetBaseService

JOB_CREATE_HASH_NAME: str = 'job_create:{jid}'

JobData = dict[str, Any]


class JobService(RedisSortedsetBaseService[JobRepository, JobModel, JobCreateSchema, JobUpdateSchema]):
    FAKE_MESSAGES_DEFAULT_BULK_SIZE = 1000
    FAKE_MESSAGE_LABEL_FIELD = '_fake_message_label'

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
        except JsonSchemaValidationError as e:
            raise JobCreateException(str(e)) from e

        try:
            master: MasterModel = await self.master_service.get_by_master_id(data.salt_master)
        except ObjectNotFoundException as e:
            raise JobCreateException(str(e)) from e

        if master.status != MasterStatus.ACCEPTED:
            msg = 'Master is not accepted'
            raise JobCreateException(msg)

        try:
            data_: dict[str, str] = {
                'jid': f'{jid}-{data.jid_postfix}' if data.jid_postfix else jid,
                'fun': data.fun,
                'tgt': data.tgt,
                'tgt_type': data.tgt_type,
            }

            if 'args' in validated_data:
                data_['arg'] = json.dumps(validated_data['args'])
            if 'kwargs' in validated_data:
                data_['kwarg'] = json.dumps(validated_data['kwargs'])

            await self.rdb.hmset(
                name=create_job_hash_name,
                # TODO (i.moshkov): check and fix later
                mapping=data_,  # type: ignore[arg-type]
            )
            await self.rdb.expire(name=create_job_hash_name, time=60 * 10)

            message = CoreNewJobAsyncRequest(hash_name=create_job_hash_name, master=master.master_id)
            await send_message_to_master(message=message, message_tag='run_job')
        except redis_exceptions.RedisError as e:
            raise JobCreateException(str(e)) from e

        if projection_model:
            return await self.get_job(jid=JID(jid), projection_model=projection_model)
        else:
            return await self.get_job(jid=JID(jid))

    async def stop_job(self, jid: JID) -> None: ...  # TODO (i.moshkov): stop jobs

    async def _get_job_data_from_store(self, jid: JID) -> JobData | None:
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

    async def get_job_return_for_minion(
        self,
        jid: JID,
        minion_id: str,
    ) -> JobResult | None:
        with replace_raised(redis_exceptions.ResponseError, JobServiceException):
            data = await self.rdb.hget(name=f'job:{jid}:return', key=minion_id)

        if data is None:
            return None
        else:
            return JobResult(**json.loads(data))

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

            # TODO: maybe not need handle this exception here? It handled in global exception handler
            try:
                res.append(JobResult(**data))
            except PydanticValidationError as e:
                raise JobServiceException(str(e)) from e

        return res, next_cur

    async def get_job_all_returns(self, jid: JID) -> list[JobResult]:
        with replace_raised(redis_exceptions.ResponseError, JobServiceException):
            records = await self.rdb.hgetall(name=f'job:{jid}:return')

        res: list[JobResult] = []
        for _, ret in records.items():
            data = json.loads(ret)

            # TODO: maybe not need handle this exception here? It handled in global exception handler
            try:
                res.append(JobResult(**data))
            except PydanticValidationError as e:
                raise JobServiceException(str(e)) from e

        return res

    async def get_job_returns_count(self, jid: JID) -> int:
        returns_count = await self.rdb.hlen(name=f'job:{jid}:return')

        if not returns_count:
            return 0

        return returns_count

    async def _get_fake_jobs(
        self, cursor: int, label: str | None = None, count: int = FAKE_MESSAGES_DEFAULT_BULK_SIZE
    ) -> tuple[int, list[bytes], list[JobData]]:
        key = 'jobs'
        label_field = self.FAKE_MESSAGE_LABEL_FIELD
        count = self.FAKE_MESSAGES_DEFAULT_BULK_SIZE

        match = f'*{label_field}*'

        with replace_raised(redis_exceptions.ResponseError, JobServiceException):
            cursor, records = await self.rdb.zscan(name=key, cursor=cursor, match=match, count=count)
        matches = []
        parsed = []
        for i in records:
            data = json.loads(i[0])
            if label_field in data and (label is None or data[label_field] == label):
                matches.append(i[0])
                parsed.append(data)
        return (cursor, matches, parsed)

    async def get_fake_jobs(
        self, cursor: int, label: str | None = None, count: int = FAKE_MESSAGES_DEFAULT_BULK_SIZE
    ) -> tuple[int, list[JobData]]:
        cursor, _, parsed = await self._get_fake_jobs(label=label, cursor=cursor, count=count)
        return (cursor, parsed)

    async def get_fake_jobs_raw(
        self, cursor: int, label: str | None = None, count: int = FAKE_MESSAGES_DEFAULT_BULK_SIZE
    ) -> tuple[int, list[bytes]]:
        cursor, raw, _ = await self._get_fake_jobs(label=label, cursor=cursor, count=count)
        return (cursor, raw)

    async def delete_fake_jobs(self, label: str | None = None) -> int:
        cur = 0
        deletions = 0
        key = 'jobs'

        while True:
            cur, to_delete = await self.get_fake_jobs_raw(cursor=cur)
            if to_delete:
                with replace_raised(redis_exceptions.ResponseError, JobServiceException):
                    deletions += await self.rdb.zrem(key, *to_delete)
            if cur == 0:
                return deletions


async def get_job_service(
    rdb: RedisDependency,
    job_repository: Annotated[JobRepository, Depends(get_job_repository)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> JobService:
    return JobService(
        rdb=rdb, job_repository=job_repository, job_schema_service=job_schema_service, master_service=master_service
    )
