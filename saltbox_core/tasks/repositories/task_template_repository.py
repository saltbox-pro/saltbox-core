from typing import Annotated, Any, ClassVar, TypeVar, overload, override

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.tasks.schemas.task_template_schemas import TaskTemplateModel

# from saltbox_core.config import logger
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskTemplateRepository(BaseMongoRepository[TaskTemplateModel]):
    class Meta:
        collection_name = 'task_templates'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']

    @overload
    async def get_list(self, query: dict[str, Any] | None, limit: int, skip: int) -> list[TaskTemplateModel]: ...

    @overload
    async def get_list(
        self,
        query: dict[str, Any] | None,
        limit: int,
        skip: int,
        projection_model: type[ProjectionModel],
    ) -> list[ProjectionModel]: ...

    @override
    async def get_list(
        self,
        query: dict[str, Any] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection_model: type[ProjectionModel] | None = None,
    ) -> list[TaskTemplateModel] | list[ProjectionModel]:
        projection = self._get_projection_from_model(projection_model) if projection_model else None
        # result = self.collection.find(filter=query, projection=projection, limit=limit, skip=skip)
        pipeline: list[dict[str, Any]] = [
            {'$match': query or {}},
            {
                '$lookup': {
                    'from': 'settings_sls_repos',
                    'localField': 'repo_id',
                    'foreignField': '_id',
                    'as': 'repo_info',
                    'pipeline': [{'$project': {'repo_url': 1, 'name': 1}}],
                }
            },
            {'$unwind': '$repo_info'},
        ]
        if skip:
            pipeline.append({'$skip': skip})
        if limit:
            pipeline.append({'$limit': limit})

        if projection:
            pipeline.append({'$project': projection})
        result = await self.collection.aggregate(pipeline)

        if projection_model:
            return [projection_model.model_validate(doc) for doc in await result.to_list()]
            # return [projection_model.model_validate(doc) async for doc in result]
        else:
            return [self.default_model.model_validate(doc) for doc in await result.to_list()]


def get_task_template_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> TaskTemplateRepository:
    return TaskTemplateRepository(db)
