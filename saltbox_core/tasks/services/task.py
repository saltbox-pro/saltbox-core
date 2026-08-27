from collections.abc import Callable
from typing import Annotated, Any, TypeVar

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from redis.asyncio import Redis

from saltbox_core.config import SETTINGS, logger
from saltbox_core.db.tiq_tasks import send_notify_by_mongo_service
from saltbox_core.minion_collections.schemas.collection import CollectionModel
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.task_templates.schemas.template import TaskTemplateModel
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.tasks.policy_ordering import PolicyOrderingItem, order_ids_by_requirements
from saltbox_core.tasks.repositories.task import TaskRepository, get_task_repository
from saltbox_core.tasks.schemas.task import (
    TaskCreateInputSchema,
    TaskCreateSchema,
    TaskModel,
    TaskPolicyForCollectionSchema,
    TaskRequirement,
    TaskShortForUpdateSchema,
    TaskStatusOnlySchema,
    TaskTargetMinion,
    TaskType,
    TaskUpdateSchema,
    TaskWithTargetCollectionIdOnlySchema,
)
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionCreateSchema, TaskMinionInnerIdOnly
from saltbox_core.tasks.schemas.tasks_status import TaskStatus, TaskStatusCreateSchema
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.tasks.services.tasks_status import TaskStatusService, get_task_status_service
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.exceptions import ObjectNotFoundException, SaltBoxValidationException
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
        collections_service: CollectionService,
        minion_service: MinionService,
        pillar_service: PillarService | None = None,
    ):
        super().__init__(repo=repo, rdb=rdb)

        self.task_status_service = task_status_service
        self.task_template_service = task_template_service
        self.task_minion_service = task_minion_service
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
                    template_id=task_template.id, data=task_data
                )
            except JsonSchemaValidationError as err:
                raise SaltBoxValidationException(str(err)) from err

        elif data.fun:
            fun = data.fun
            validated_data = task_data
        else:
            msg = 'Either task_template_id or fun must be provided'
            raise SaltBoxValidationException(msg)

        task_arg = validated_data.get('args')
        task_kwarg = validated_data.get('kwargs')

        if task_template and task_template.fun == 'state.apply':
            task_kwarg = {} if not task_kwarg else task_kwarg

            if 'mods' not in task_kwarg:
                task_kwarg['mods'] = task_template.name

        return fun, task_arg, task_kwarg

    async def __parse_input_create_schema(self, data: TaskCreateInputSchema) -> tuple[TaskCreateSchema, dict[str, Any]]:
        try:
            if data.collection_slug:
                collection = await self.collections_service.get_by_slug(
                    slug=data.collection_slug, projection_model=EmptyModel
                )
            elif data.collection_id:
                collection = await self.collections_service.get(query=data.collection_id, projection_model=EmptyModel)
            else:
                msg = 'Collection must be provided'
                raise SaltBoxValidationException(msg)
        except ObjectNotFoundException as e:
            msg = 'Collection not found'
            raise SaltBoxValidationException(msg) from e

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

        if task_template and task_template.query:
            target_query = {'$and': [task_template.query, data.query]} if data.query else task_template.query
        else:
            target_query = data.query

        return TaskCreateSchema.model_validate(
            {
                'task_type': data.task_type,
                'description': data.description,
                'weight': data.weight,
                'requirements': data.requirements,
                'task_template_id': data.task_template_id,
                'fun': fun,
                'arg': task_arg,
                'kwarg': task_kwarg,
                'target_collection_id': collection.id,
                'target_query': target_query,
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

    async def __validate_requirements(
        self,
        target_collection_id: PyObjectId,
        requirements: list[TaskRequirement],
        *,
        exclude_task_id: PyObjectId | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        if not requirements:
            return

        requirement_task_ids = [requirement.task_id for requirement in requirements]

        if exclude_task_id is not None and exclude_task_id in requirement_task_ids:
            msg = 'A policy cannot list itself as a requirement'
            raise SaltBoxValidationException(msg)

        referenced_tasks = await self.get_list(
            query={'_id': {'$in': requirement_task_ids}},
            session=session,
            projection_model=TaskWithTargetCollectionIdOnlySchema,
        )
        referenced_by_id = {task.id: task for task in referenced_tasks}

        missing_ids = [task_id for task_id in requirement_task_ids if task_id not in referenced_by_id]
        if missing_ids:
            msg = f'Requirement task(s) not found: {", ".join(str(task_id) for task_id in missing_ids)}'
            raise SaltBoxValidationException(msg)

        wrong_collection_ids = [
            str(task_id)
            for task_id in requirement_task_ids
            if referenced_by_id[task_id].target_collection_id != target_collection_id
        ]
        if wrong_collection_ids:
            msg = (
                'Requirement task(s) must belong to the same collection as the policy: '
                f'{", ".join(wrong_collection_ids)}'
            )
            raise SaltBoxValidationException(msg)

    async def __get_minions_by_targeting(
        self,
        task_id: PyObjectId,
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

        minions_in_task = await self.task_minion_service.get_list(
            query={'task_id': task_id},
            session=session,
            projection_model=TaskMinionInnerIdOnly,
        )
        if minions_in_task:
            queries.append({'_id': {'$nin': [minion.minion_inner_id for minion in minions_in_task]}})

        return [
            minion.id
            for minion in await self.minion_service.get_list(
                query={'$and': queries} if queries else {},
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
            task_id=task_id,
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
            validated_data = TaskCreateInputSchema.model_validate(data)
        else:
            validated_data = data

        async with get_mongo_session_with_transaction(session) as s:
            try:
                save_pillars_as_default = validated_data.save_pillars_as_default
                logger.debug(f'Save as default: {save_pillars_as_default}')
                creation_data, pillars = await self.__parse_input_create_schema(data=validated_data)
                await self.__validate_requirements(
                    target_collection_id=creation_data.target_collection_id,
                    requirements=creation_data.requirements,
                    session=s,
                )

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
                        user=validated_data.user,
                        save_as_default=save_pillars_as_default,
                        session=s,
                    )

                logger.debug(f'Transaction committed successfully for task {task.id}')
            except Exception:
                logger.exception('Error during task creation, aborting transaction')
                raise

        await self.task_status_service.create(
            data=TaskStatusCreateSchema.model_validate({'task_id': task.id, 'type': TaskStatus.created}),
            session=session,
        )

        await self.fill_task_minions(
            task_id=task.id,
            target_collection_id=task.target_collection_id,
            target_query=task.target_query,
            target_minions=validated_data.minions,
            session=session,
            notify=False,
        )

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
        obj = await self.get(query=query, session=session, projection_model=TaskShortForUpdateSchema)

        new_status = None
        if hasattr(data, 'status'):
            new_status = data.status
        elif isinstance(data, dict) and 'status' in data:
            new_status = data.pop('status')

        requirements = None
        if isinstance(data, BaseModel):
            if 'requirements' in data.model_fields_set:
                requirements = data.requirements
        elif isinstance(data, dict) and 'requirements' in data:
            requirements = [
                item if isinstance(item, TaskRequirement) else TaskRequirement.model_validate(item)
                for item in data['requirements']
            ]

        if requirements is not None:
            await self.__validate_requirements(
                target_collection_id=obj.target_collection_id,
                requirements=requirements,
                exclude_task_id=obj.id,
                session=session,
            )

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

    async def get_policies_for_collection(
        self, target_collection_id: PyObjectId
    ) -> list[TaskPolicyForCollectionSchema]:
        policies = await self.get_list(
            query={'task_type': TaskType.policy, 'target_collection_id': target_collection_id},
            projection_model=TaskPolicyForCollectionSchema,
        )

        by_task_id = {policy.id: policy for policy in policies}
        ordering_items = [
            PolicyOrderingItem(id=policy.id, weight=policy.weight, requirements=policy.requirements)
            for policy in policies
        ]

        return [by_task_id[task_id] for task_id in order_ids_by_requirements(ordering_items)]

    async def get_task_statuses(self, task_ids: list[PyObjectId]) -> dict[PyObjectId, TaskStatus]:
        if not task_ids:
            return {}

        tasks = await self.get_list(
            query={'_id': {'$in': task_ids}},
            projection_model=TaskStatusOnlySchema,
        )

        return {task.id: task.status.type for task in tasks}


def get_task_service(
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
    rdb: Annotated[Redis, Depends(get_redis)],
    task_status_service: Annotated[TaskStatusService, Depends(get_task_status_service)],
    task_template_service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
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
        collections_service=collections_service,
        minion_service=minion_service,
        pillar_service=pillar_service,
    )
