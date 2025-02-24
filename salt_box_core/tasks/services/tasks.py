import json
from datetime import UTC, datetime
from typing import Annotated, Any, TypeVar, overload

from fastapi import Depends
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel
from redis.asyncio import Redis

from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.db.redis import RedisDependency
from salt_box_core.tasks.repositories.task_repository import TaskRepository, get_task_repository
from salt_box_core.tasks.schemas.task_schemas import (
    TaskCreateFromTemplateSchema,
    TaskCreateSchema,
    TaskModel,
    TaskStatus,
    TaskTemplateShort,
    TaskUpdateSchema,
)
from salt_box_core.tasks.schemas.task_template_schemas import (
    TaskTemplateModel,
)
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService, get_task_template_service
from salt_box_core.utilities.exceptions import ObjectDoesNotExistError, ServiceError
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskService(MongoBaseService[TaskRepository, TaskModel, TaskCreateFromTemplateSchema, TaskUpdateSchema]):
    repository_class = TaskRepository

    def __init__(self, repo: TaskRepository, rdb: Redis, task_template_service: TaskTemplateService):
        super().__init__(repo=repo)

        self.task_template_service = task_template_service
        self.rdb = rdb

    @overload
    async def create(
        self,
        data: TaskCreateFromTemplateSchema,
        projection_model: None = None,
        notify: bool = True,
    ) -> TaskModel: ...

    @overload
    async def create(
        self,
        data: TaskCreateFromTemplateSchema,
        projection_model: type[ProjectionModel],
        notify: bool = True,
    ) -> ProjectionModel: ...

    async def create(
        self,
        data: TaskCreateFromTemplateSchema,
        projection_model: type[ProjectionModel] | None = None,
        notify: bool | None = None,
    ) -> TaskModel | ProjectionModel:
        task_template: TaskTemplateModel = await self.task_template_service.get(query=data.task_template_id)

        try:
            validated_data: dict = await self.task_template_service.get_validated_data(
                name=task_template.name,
                sid=task_template.repo_id,
                data=data.data.model_dump(exclude_none=True, by_alias=True) if data.data else {},
            )
        except JsonSchemaValidationError as err:
            raise ServiceError(err) from err

        task_args = validated_data['args'] if 'args' in validated_data else []
        task_kwargs = validated_data['kwargs'] if 'kwargs' in validated_data else {}

        if task_template.fun == 'state.apply' and 'moods' not in task_kwargs:
            task_kwargs['mods'] = task_template.name

        creation_data = TaskCreateSchema.model_validate(
            {
                'task_template': TaskTemplateShort(**task_template.model_dump()),
                'fun': task_template.fun,
                'task_args': task_args,
                'task_kwargs': task_kwargs,
                'collection_id': data.collection_id,
                'query': data.query,
                'minions': data.minions,
                'batch_size': data.batch_size,
                'max_retries': data.max_retries,
                'user': data.user,
            }
        )

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
                    TaskStatus.finished: 'finished_dt',
                }.get(data.status)

                if stamp_field_name:
                    data.__setattr__(stamp_field_name, datetime.now(UTC))

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
) -> TaskService:
    return TaskService(repo=repo, rdb=rdb, task_template_service=task_template_service)
