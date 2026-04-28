from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from redis.asyncio import Redis

from saltbox_core.config import SETTINGS, logger
from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.minion_collections.schemas.collection_schemas import CollectionModel
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.tasks.exceptions import (
    TaskCreateSchemaValidationException,
    TaskCreateServiceException,
    TaskServiceException,
)
from saltbox_core.tasks.repositories.task import TaskRepository, get_task_repository
from saltbox_core.tasks.schemas.task import (
    TaskCreateInputSchema,
    TaskCreateSchema,
    TaskModel,
    TaskTargetMinion,
    TaskUpdateSchema,
)
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema
from saltbox_core.tasks.schemas.tasks_status import TaskStatus, TaskStatusCreateSchema
from saltbox_core.tasks.schemas.tasks_template import TaskTemplateModel
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.tasks.services.tasks_status import TaskStatusService, get_task_status_service
from saltbox_core.tasks.services.tasks_template import TaskTemplateService, get_task_template_service
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.serivces.mongo_base_with_notify_service import MongoBaseWithNotifyService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskService(MongoBaseWithNotifyService[TaskRepository, TaskModel, TaskCreateInputSchema, TaskUpdateSchema]):
    repository_class = TaskRepository

    def __init__(
        self,
        repo: TaskRepository,
        rdb: Redis,
        task_status_service: TaskStatusService,
        task_template_service: TaskTemplateService,
        task_minion_service: TaskMinionService,
        job_schema_service: JobSchemaService,
        collections_service: CollectionService,
        minion_service: MinionService,
        pillar_service: PillarService | None = None,
    ):
        super().__init__(repo=repo, rdb=rdb)

        self.task_status_service = task_status_service
        self.task_template_service = task_template_service
        self.task_minion_service = task_minion_service
        self.job_schema_service = job_schema_service
        self.collections_service = collections_service
        self.minion_service = minion_service
        self.pillar_service = pillar_service
        self.rdb = rdb

    @property
    def notify_taskiq_task(self) -> Callable:
        return send_notify_by_mongo_service

    @property
    def service_name(self) -> str:
        return 'task_service'

    def _get_notify_channel(self, obj: TaskModel | ProjectionModel, action: str) -> str | None:
        if not hasattr(obj, 'id'):
            return None

        return {
            'create': f'task:{obj.id}:create',
            'update': f'task:{obj.id}:update',
            'delete': f'task:{obj.id}:delete',
        }.get(action)

    async def __parse_salt_fun_params(
        self, data: TaskCreateInputSchema, task_template: TaskTemplateModel | None = None
    ) -> tuple[str, list | None, dict | None]:
        task_data: dict = {}
        if data.data and data.data.args:
            task_data['args'] = data.data.args
        if data.data and data.data.kwargs:
            task_data['kwargs'] = data.data.kwargs

        if not task_template and data.task_template_id:
            task_template = await self.task_template_service.get(query=data.task_template_id)

        if task_template:
            fun = task_template.fun

            try:
                validated_data = await self.task_template_service.get_validated_data(
                    name=task_template.name, sid=task_template.repo_id, data=task_data
                )
            except JsonSchemaValidationError as err:
                raise TaskCreateSchemaValidationException(str(err)) from None

        elif data.fun:
            fun = data.fun

            try:
                validated_data = await self.job_schema_service.get_validated_data(name=fun, data=task_data)
            except JsonSchemaValidationError as err:
                raise TaskServiceException(str(err)) from err
        else:
            msg = 'Task salt fun must be provided from direct fun or task template'
            raise TaskCreateServiceException(msg)

        task_arg = validated_data.get('args')
        task_kwarg = validated_data.get('kwargs')

        if task_template and task_template.fun == 'state.apply':
            task_kwarg = {} if not task_kwarg else task_kwarg

            if 'mods' not in task_kwarg:
                task_kwarg['mods'] = task_template.name

        return fun, task_arg, task_kwarg

    async def __parse_input_create_schema(self, data: TaskCreateInputSchema) -> tuple[TaskCreateSchema, dict[str, Any]]:
        if data.collection_slug:
            collection = await self.collections_service.get_by_slug(
                slug=data.collection_slug, projection_model=EmptyModel
            )
            collection_id = collection.id
        elif data.collection_id:
            collection_id = data.collection_id
        else:
            msg = 'Collection must be provided'
            raise TaskCreateServiceException(msg)

        task_template: TaskTemplateModel | None = None

        task_defaults = {
            'batch_size': SETTINGS.tasks_defaults_batch_size,
            'max_jobs_count_at_same_time': SETTINGS.tasks_defaults_max_jobs_count_at_same_time,
            'max_retries': SETTINGS.tasks_defaults_max_retries,
            'retry_delay': SETTINGS.tasks_defaults_retry_delay,
        }

        if data.task_template_id:
            task_template = await self.task_template_service.get(query=data.task_template_id)

            if task_template.defaults:
                task_defaults.update(task_template.defaults.model_dump())

        fun, task_arg, task_kwarg = await self.__parse_salt_fun_params(data=data, task_template=task_template)

        if task_kwarg:
            pillars = task_kwarg.pop('pillar', {})
        else:
            pillars = {}

        return TaskCreateSchema.model_validate(
            {
                'task_type': data.task_type,
                'task_template_id': data.task_template_id,
                'fun': fun,
                'arg': task_arg,
                'kwarg': task_kwarg,
                'target_collection_id': collection_id,
                'target_query': data.query,
                'batch_size': data.batch_size if data.batch_size is not None else task_defaults['batch_size'],
                'max_retries': data.max_retries if data.max_retries is not None else task_defaults['max_retries'],
                'retry_delay': data.retry_delay if data.retry_delay is not None else task_defaults['retry_delay'],
                'ttl': data.ttl,
                'max_jobs_count_at_same_time': (
                    data.max_jobs_count_at_same_time
                    if data.max_jobs_count_at_same_time is not None
                    else task_defaults['max_jobs_count_at_same_time']
                ),
                'user': data.user,
                'source': data.source,
            }
        ), pillars

    async def __get_minions_by_targeting(
        self,
        target_collection: CollectionModel,
        target_query: dict | None = None,
        target_minions: list[TaskTargetMinion] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> list[PyObjectId]:
        queries = [target_collection.full_query] if target_collection.full_query else []
        if target_query:
            queries.append(target_query)
        if target_minions:
            queries.append(
                {
                    '$or': [
                        {'minion_id': target_minion.minion_id, 'master': target_minion.salt_master}
                        for target_minion in target_minions
                    ]
                }
            )

        return [
            minion.id
            for minion in await self.minion_service.get_list(
                query={'$and': queries} if queries else {},
                limit=0,
                skip=0,
                session=session,
                projection_model=EmptyModel,
            )
        ]

    async def fill_task_minions(
        self,
        task_id: PyObjectId,
        target_collection_id: PyObjectId,
        target_query: dict | None = None,
        target_minions: list[TaskTargetMinion] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
        notify: bool = True,
    ) -> int:
        collection = await self.collections_service.get(query=target_collection_id)

        minion_ids = await self.__get_minions_by_targeting(
            target_collection=collection,
            target_query=target_query,
            target_minions=target_minions,
            session=session,
        )

        created_minions_ids = await self.task_minion_service.bulk_create(
            data=[
                TaskMinionCreateSchema.model_validate({'task_id': task_id, 'minion_inner_id': minion_id})
                for minion_id in minion_ids
            ],
            session=session,
            notify=notify,
        )

        return len(created_minions_ids)

    async def process(self, task_id: PyObjectId, *, session: MongoAsyncClientSession | None = None) -> None:
        async with self.rdb.lock(f'task-process-{task_id!s}'):
            logger.debug(f'Task process {task_id} started')

    async def create(
        self,
        data: TaskCreateInputSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
        notify: bool = True,
    ) -> PyObjectId:
        if isinstance(data, dict):
            data = TaskCreateInputSchema.model_validate(data)

        async with get_mongo_session_with_transaction(session) as s:
            try:
                save_pillars_as_default = data.save_pillars_as_default
                logger.debug(f'Save as default: {save_pillars_as_default}')
                creation_data, pillars = await self.__parse_input_create_schema(data=data)

                task_id = await self.repo.create(data=creation_data, session=s)
                task = await self.get(query=task_id, session=s)
                secret_pillar_names = None

                if task.task_template_id:
                    tpl = await self.task_template_service.get(query=task.task_template_id)
                    secret_pillar_names = tpl.secret_pillars

                if self.pillar_service and pillars:
                    logger.debug(f'Creating pillars for task {task.id}')
                    await self.pillar_service.create_for_task(
                        task_id=task.id,
                        task_template_id=task.task_template_id,
                        pillars=pillars,
                        secret_pillar_names=secret_pillar_names,
                        user=data.user,
                        save_as_default=save_pillars_as_default,
                        session=s,
                    )
                await self.task_status_service.create(
                    data=TaskStatusCreateSchema.model_validate(
                        {
                            'task_id': task.id,
                            'type': TaskStatus.created,
                        }
                    ),
                    session=s,
                )

                await self.fill_task_minions(
                    task_id=task.id,
                    target_collection_id=task.target_collection_id,
                    target_query=task.target_query,
                    target_minions=data.minions,
                    session=s,
                    notify=False,
                )

                logger.debug(f'Transaction committed successfully for task {task.id}')
            except Exception:
                logger.exception('Error during task creation, aborting transaction')
                raise

        if notify:
            await self._notify(obj_id=task_id, action='create')

        return task_id

    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: TaskUpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
        *,
        operator: MongoUpdateOperator = MongoUpdateOperator.set,
        session: MongoAsyncClientSession | None = None,
        notify: bool = True,
    ) -> PyObjectId:
        obj = await self.get(query=query, projection_model=TaskModel, session=session)

        new_status = None
        if hasattr(data, 'status'):
            new_status = data.status
        elif isinstance(data, dict) and 'status' in data:
            new_status = data.pop('status')

        if new_status and obj.status.type != new_status:
            await self.task_status_service.create(
                data=TaskStatusCreateSchema.model_validate(
                    {
                        'task_id': obj.id,
                        'type': new_status,
                    }
                ),
            )

        return await super().update(
            query=query,
            data=data,
            exclude_unset=exclude_unset,
            operator=operator,
            session=session,
            notify=notify,
        )


def get_task_service(
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
    task_status_service: Annotated[TaskStatusService, Depends(get_task_status_service)],
    task_template_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    collections_service: Annotated[CollectionService, Depends(get_collection_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    pillar_service: Annotated[PillarService | None, Depends(get_pillar_service)] = None,
) -> TaskService:
    return TaskService(
        repo=repo,
        rdb=rdb,
        task_status_service=task_status_service,
        task_template_service=task_template_service,
        task_minion_service=task_minion_service,
        job_schema_service=job_schema_service,
        collections_service=collections_service,
        minion_service=minion_service,
        pillar_service=pillar_service,
    )
