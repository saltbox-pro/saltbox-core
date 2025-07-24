import json
from typing import Annotated, Any, TypeVar, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from redis.asyncio import Redis

from saltbox_core.jobs.services.job_sc_service import JobSchemaService, get_job_schema_service
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.tasks.repositories.task_repository import TaskRepository, get_task_repository
from saltbox_core.tasks.schemas.task_schemas import (
    CollectionShort,
    TaskCreateInputSchema,
    TaskCreateSchema,
    TaskModel,
    TaskPostProcessing,
    TaskStatus,
    TaskTemplateShort,
    TaskUpdateSchema,
)
from saltbox_core.tasks.schemas.task_template_schemas import (
    TaskTemplateModel,
)
from saltbox_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service
from saltbox_core.utilities.exceptions import ObjectDoesNotExistError, ServiceError
from saltbox_sdk.db.exceptions import ObjectNotFoundError
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import RedisDependency
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.utilities.helpers import utc_now

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskService(MongoBaseService[TaskRepository, TaskModel, TaskCreateInputSchema, TaskUpdateSchema]):
    repository_class = TaskRepository

    def __init__(
        self,
        repo: TaskRepository,
        rdb: Redis,
        task_template_service: TaskTemplateService,
        job_schema_service: JobSchemaService,
        collections_service: CollectionService,
    ):
        super().__init__(repo=repo)

        self.task_template_service = task_template_service
        self.job_schema_service = job_schema_service
        self.collections_service = collections_service
        self.rdb = rdb

    async def __parse_input_create_schema(self, data: TaskCreateInputSchema) -> TaskCreateSchema:
        task_data: dict = data.data.model_dump(exclude_none=True, by_alias=True) if data.data else {}
        validated_data: dict = {}
        task_template: TaskTemplateModel | None = None
        fun: str = ''

        if not data.task_template_id and not data.fun:
            msg = 'One of `task_template_id` or `fun` is required'
            raise ServiceError(msg)

        elif data.task_template_id and data.fun:
            msg = 'Only one of `task_template_id` or `fun` is set at same time'
            raise ServiceError(msg)

        elif data.task_template_id:
            task_template = await self.task_template_service.get(query=data.task_template_id)
            fun = task_template.fun

            try:
                validated_data = await self.task_template_service.get_validated_data(
                    name=task_template.name, sid=task_template.repo_id, data=task_data
                )
            except JsonSchemaValidationError as err:
                raise ServiceError(err) from err

        elif data.fun:
            fun = data.fun

            try:
                validated_data = await self.job_schema_service.get_validated_data(name=fun, data=task_data)
            except JsonSchemaValidationError as err:
                raise ServiceError(err) from err

        collection = await self.collections_service.get(query=data.collection_id)

        task_args = validated_data['args'] if 'args' in validated_data else None
        task_kwargs = validated_data['kwargs'] if 'kwargs' in validated_data else None

        if task_template and task_template.fun == 'state.apply':
            task_kwargs = {} if not task_kwargs else task_kwargs

            if 'mods' not in task_kwargs:
                task_kwargs['mods'] = task_template.name

        return TaskCreateSchema.model_validate(
            {
                'parent_task_id': data.parent_task_id,
                'task_template': TaskTemplateShort(**task_template.model_dump()) if task_template else None,
                'fun': fun,
                'task_args': task_args,
                'task_kwargs': task_kwargs,
                'target_collection': CollectionShort(**collection.model_dump()),
                'target_query': data.query,
                'target_minions': data.minions,
                # TODO (i.moshkov): collect masters from store
                'target_masters': data.salt_masters if data.salt_masters else ['salt-master'],
                'batch_size': data.batch_size,
                'max_retries': data.max_retries,
                'max_jobs_count_at_same_time': data.max_jobs_count_at_same_time,
                'user': data.user,
            }
        )

    @overload
    async def create(
        self,
        data: TaskCreateInputSchema,
        projection_model: None = None,
        notify: bool = True,
    ) -> TaskModel: ...

    @overload
    async def create(
        self,
        data: TaskCreateInputSchema,
        projection_model: type[ProjectionModel],
        notify: bool = True,
    ) -> ProjectionModel: ...

    async def create(
        self,
        data: TaskCreateInputSchema,
        projection_model: type[ProjectionModel] | None = None,
        notify: bool | None = None,
    ) -> TaskModel | ProjectionModel:
        creation_data: TaskCreateSchema = await self.__parse_input_create_schema(data=data)

        if data.postprocessing:
            creation_data.postprocessing = TaskPostProcessing.model_validate(data.postprocessing.model_dump())

        if projection_model:
            task: TaskModel | ProjectionModel = await self.repo.create(creation_data, projection_model=projection_model)
        else:
            task = await self.repo.create(creation_data)

        if notify and hasattr(task, 'id'):
            await self.rdb.publish(channel=f'task:{task.id}:create', message=self.__prepare_pub_message(task))

        return task

    @overload
    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: TaskUpdateSchema | dict[str, Any],
        notify: bool = True,
    ) -> TaskModel: ...

    @overload
    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: TaskUpdateSchema | dict[str, Any],
        notify: bool = True,
        *,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: TaskUpdateSchema | dict[str, Any],
        notify: bool = True,
        *,
        projection_model: type[ProjectionModel] | None = None,
    ) -> TaskModel | ProjectionModel:
        try:
            obj = await self.get(query=query, projection_model=TaskModel)

            if hasattr(data, 'status') and obj.status != data.status:
                stamp_field_name = {
                    TaskStatus.running: 'run_dt',
                    TaskStatus.stopped: 'stopped_dt',
                    TaskStatus.postprocessing: 'postprocessing_dt',
                    TaskStatus.finished: 'finished_dt',
                }.get(data.status)

                if stamp_field_name:
                    data.__setattr__(stamp_field_name, utc_now())

            if projection_model:
                updated_obj: TaskModel | ProjectionModel = await self.repo.update(
                    query=query, data=data, projection_model=projection_model
                )
            else:
                updated_obj = await self.repo.update(query=query, data=data)
        except ObjectNotFoundError as e:
            msg = 'Object does not found'
            raise ObjectDoesNotExistError(msg) from e

        if isinstance(notify, bool) and notify and hasattr(updated_obj, 'id'):
            await self.rdb.publish(
                channel=f'task:{updated_obj.id}:update', message=self.__prepare_pub_message(updated_obj)
            )

        return updated_obj

    @overload
    async def delete(self, query: dict[str, Any] | PyObjectId) -> int: ...

    @overload
    async def delete(self, query: dict[str, Any] | PyObjectId, notify: bool = True) -> int: ...

    async def delete(self, query: dict[str, Any] | PyObjectId, notify: bool | None = None) -> int:
        obj = await self.get(query=query)
        deleted_count: int = await super().delete(query=query)

        if isinstance(notify, bool) and notify:
            await self.rdb.publish(channel=f'task:{obj.id}:delete', message=self.__prepare_pub_message(obj))

        return deleted_count

    @staticmethod
    def __prepare_pub_message(obj: BaseModel) -> str:
        data: dict = obj.model_dump(by_alias=True, mode='json')

        if 'id' in data:
            data['_id'] = data['id']

        return json.dumps(data)


async def get_task_service(
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
    rdb: RedisDependency,
    task_template_service: Annotated[TaskTemplateService, Depends(get_task_template_service)],
    job_schema_service: Annotated[JobSchemaService, Depends(get_job_schema_service)],
    collections_service: Annotated[CollectionService, Depends(get_collection_service)],
) -> TaskService:
    return TaskService(
        repo=repo,
        rdb=rdb,
        task_template_service=task_template_service,
        job_schema_service=job_schema_service,
        collections_service=collections_service,
    )
