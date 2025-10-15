import json
from typing import Annotated, Any, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from redis import exceptions as redis_exceptions
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.exceptions import JobCreateException, JobServiceException
from saltbox_core.jobs.repositories.job_repository import JobRepository, get_job_repository
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel, JobUpdateSchema
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.utilities.context import replace_raised
from saltbox_core.utilities.jid import JID
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.fastapi_utils.dependencies import RedisDependency
from saltbox_sdk.serivces.mongo_base_service import ProjectionModel
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService

JOBS_TO_CREATE_SET_NAME: str = 'jobs:{master_id}:to_create'

JobData = dict[str, Any]


class JobService(MongoBaseWithNotifyService[JobRepository, JobModel, JobCreateSchema, JobUpdateSchema]):
    FAKE_MESSAGES_DEFAULT_BULK_SIZE = 1000
    FAKE_MESSAGE_LABEL_FIELD = '_fake_message_label'

    def __init__(
        self,
        rdb: Redis,
        job_repository: JobRepository,
        job_schema_service: JobSchemaService,
        master_service: MasterService,
    ):
        self.job_schema_service = job_schema_service
        self.master_service = master_service
        super().__init__(repo=job_repository, rdb=rdb)

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

    async def _notify(self, obj: JobModel | ProjectionModel, action: str) -> None:
        try:
            channel = self._get_notify_channel(obj=obj, action=action)
            task_channel = self._get_notify_channel(obj=obj, action=f'{action}_task')

            async with self.rdb.pipeline() as pipe:
                if channel:
                    await self.rdb.publish(channel=channel, message=self._prepare_pub_message(obj=obj))
                if task_channel:
                    await self.rdb.publish(channel=task_channel, message=self._prepare_pub_message(obj=obj))

                await pipe.execute()
        except redis_exceptions.RedisError as e:
            logger.error(e)

    @overload  # type: ignore
    async def create(
        self,
        data: JobCreateSchema,
        notify: bool = True,
    ) -> JobModel: ...

    @overload
    async def create(
        self,
        data: JobCreateSchema,
        projection_model: type[ProjectionModel],
        notify: bool = True,
    ) -> ProjectionModel: ...

    async def create(  # type: ignore
        self,
        data: JobCreateSchema,
        projection_model: type[ProjectionModel] | None = None,
        notify: bool = True,
    ) -> JobModel | ProjectionModel:
        if not data.jid:
            data.jid = str(JID.generate())

        try:
            await self.master_service.get_accepted_by_master_id(data.salt_master)
        except ObjectNotFoundException as e:
            raise JobCreateException(str(e)) from e

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

        job: JobModel | ProjectionModel
        try:
            create_args: dict[str, Any] = {'data': data}
            if projection_model:
                create_args['projection_model'] = projection_model
            if notify:
                create_args['notify'] = notify

            job = await super().create(**create_args)
        except redis_exceptions.RedisError as e:
            raise JobCreateException(str(e)) from e

        await self.rdb.rpush(
            JOBS_TO_CREATE_SET_NAME.format(master_id=data.salt_master),
            json.dumps(
                {
                    'jid': data.jid,
                    'tgt': data.tgt,
                    'tgt_type': data.tgt_type,
                    'fun': data.fun,
                    'args': data.arg,
                    'kwargs': data.kwarg,
                }
            ),
        )

        if notify and hasattr(job, 'id'):
            await self._notify(obj=job, action='create')

        return job

    async def stop_job(self, jid: JID) -> None: ...  # TODO (i.moshkov): stop jobs

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
    rdb: RedisDependency,
    job_repository: Annotated[JobRepository, Depends(get_job_repository)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> JobService:
    return JobService(
        rdb=rdb, job_repository=job_repository, job_schema_service=job_schema_service, master_service=master_service
    )
