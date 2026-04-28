import json
from collections.abc import Callable
from typing import Annotated, Any, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from saltbox_bridge_messages import MasterStatus
from saltbox_core.config import SETTINGS, logger
from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.jobs.exceptions import JobCreateException, JobServiceException
from saltbox_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnStatus
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel, JobSimpleSchema, JobStatus, JobUpdateSchema
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.utilities.context import replace_raised
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.serivces.mongo_base_service import ProjectionModel
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService

JOBS_TO_CREATE_SET_NAME: str = 'jobs:{master_id}:to_create'

JobData = dict[str, Any]


class JobService(MongoBaseWithNotifyService[JobRepository, JobModel, JobCreateSchema, JobUpdateSchema]):
    FAKE_MESSAGES_DEFAULT_BULK_SIZE = 1000
    FAKE_MESSAGE_LABEL_FIELD = '_fake_message_label'
    SALT_FUNCS_TO_ADD_PILLARENV = (
        'pillar.data',
        'pillar.fetch',
        'pillar.get',
        'pillar.item',
        'pillar.items',
        'pillar.ls',
        'pillar.obfuscate',
        'state.apply',
    )

    def __init__(
        self,
        rdb: Redis,
        job_repository: JobRepository,
        job_schema_service: JobSchemaService,
        job_return_service: JobReturnService,
        master_service: MasterService,
    ):
        self.job_schema_service = job_schema_service
        self.job_return_service = job_return_service
        self.master_service = master_service
        super().__init__(repo=job_repository, rdb=rdb)

    @property
    def notify_taskiq_task(self) -> Callable:
        return send_notify_by_mongo_service

    @property
    def service_name(self) -> str:
        return 'job_service'

    def _get_notify_channel(self, obj: JobModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'jid'):
            return None

        channels: dict[str, str] = {
            'create': f'job:{obj.jid}:create',
            'update': f'job:{obj.jid}:update',
            'delete': f'job:{obj.jid}:delete',
        }

        if hasattr(obj, 'source') and obj.source:
            if obj.source.type == 'task':
                channels.update(
                    {
                        'create_task': f'task:{obj.source.id}:job:{obj.jid}:create',
                        'update_task': f'task:{obj.source.id}:job:{obj.jid}:update',
                        'delete_task': f'task:{obj.source.id}:job:{obj.jid}:delete',
                    }
                )

        return channels.get(action)

    async def run_notify(self, obj_id: PyObjectId, action: str) -> None:
        obj = await self.get(query=obj_id)

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

    async def __prepare_create_obj(self, data: JobCreateSchema) -> None:
        if not data.jid:
            data.jid = str(JID.generate())

        if data.ttl is None:
            data.ttl = await self.job_schema_service.get_ttl(name=data.fun)
        elif data.ttl == 0:
            data.ttl = SETTINGS.jobs_max_ttl

        try:
            data_to_validate: dict[str, Any] = {}
            if data.arg:
                data_to_validate['args'] = data.arg
            if data.kwarg:
                data_to_validate['kwargs'] = data.kwarg
            validated_data = await self.job_schema_service.get_validated_data(name=data.fun, data=data_to_validate)
            data.arg = validated_data.get('args')
            data.kwarg = validated_data.get('kwargs')
        except JsonSchemaValidationError as e:
            raise JobCreateException(str(e)) from e

    async def create(
        self,
        data: JobCreateSchema | dict[str, Any],
        *,
        extra_pillarenv: list[str] | None = None,
        session: MongoAsyncClientSession | None = None,
        notify: bool = True,
    ) -> PyObjectId:
        if isinstance(data, dict):
            data = JobCreateSchema.model_validate(data)

        if not await self.master_service.exists(
            query={'status': MasterStatus.ACCEPTED, 'master_id': data.salt_master}, session=session
        ):
            msg = 'Master not found'
            raise JobCreateException(msg)

        await self.__prepare_create_obj(data=data)

        create_args: dict[str, Any] = {'data': data}
        if notify:
            create_args['notify'] = notify

        job_id = await super().create(**create_args, session=session)

        job_salt_data: dict[str, Any] = {
            'jid': data.jid,
            'tgt': data.tgt,
            'tgt_type': data.tgt_type,
            'fun': data.fun,
            'arg': data.arg,
            'kwarg': data.kwarg,
        }

        if data.fun in self.SALT_FUNCS_TO_ADD_PILLARENV:
            if not data.kwarg:
                data.kwarg = {}

            pillarenv = ['base']

            if extra_pillarenv:
                pillarenv.extend(extra_pillarenv)

            if job_salt_data['kwarg'] is None:
                job_salt_data['kwarg'] = {}

            job_salt_data['kwarg']['pillarenv'] = ','.join(pillarenv)

        await self.rdb.rpush(JOBS_TO_CREATE_SET_NAME.format(master_id=data.salt_master), json.dumps(job_salt_data))

        return job_id

    @overload
    async def update_status(
        self,
        jid: JID,
        *,
        session: MongoAsyncClientSession | None = None,
        force: bool = False,
        notify: bool = True,
    ) -> JobModel: ...

    @overload
    async def update_status(
        self,
        jid: JID,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
        force: bool = False,
        notify: bool = True,
    ) -> ProjectionModel: ...

    async def update_status(
        self,
        jid: JID,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel] | None = None,
        force: bool = False,
        notify: bool = True,
    ) -> JobModel | ProjectionModel:
        job = await self.get(query={'jid': str(jid)}, projection_model=JobSimpleSchema)

        data_to_update = {}

        if job.status == JobStatus.running:
            if not await self.job_return_service.exists(
                query={'jid': job.jid, 'salt_master': job.salt_master, 'status': JobReturnStatus.waiting},
                session=session,
            ):
                data_to_update['status'] = JobStatus.finished

        if len(data_to_update.keys()) or force:
            await self.update(
                query=job.id,
                data=data_to_update,
                session=session,
                notify=notify,
            )

        if projection_model:
            return await self.get(query=job.id, session=session, projection_model=projection_model)

        return await self.get(query=job.id, session=session)

    async def stop_job(self, jid: JID | PyObjectId) -> None: ...  # TODO (i.moshkov): stop jobs

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


def get_job_service(
    rdb: Annotated[Redis, Depends(get_redis)],
    job_repository: Annotated[JobRepository, Depends(get_job_repository)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> JobService:
    return JobService(
        rdb=rdb,
        job_repository=job_repository,
        job_schema_service=job_schema_service,
        job_return_service=job_return_service,
        master_service=master_service,
    )
