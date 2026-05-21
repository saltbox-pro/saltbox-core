from typing import Annotated, Any, TypeVar, overload
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.minion_collections.repositories.collection_repository import (
    CollectionRepository,
    get_collection_repository,
)
from saltbox_core.minion_collections.schemas.collection_schemas import (
    CollectionCreateSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class CollectionService(
    MongoBaseService[CollectionRepository, CollectionModel, CollectionCreateSchema, CollectionUpdateSchema]
):
    @overload
    async def get_by_slug(
        self,
        slug: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> CollectionModel: ...

    @overload
    async def get_by_slug(
        self,
        slug: str,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def get_by_slug(
        self,
        slug: str,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> CollectionModel | ProjectionModel:
        if projection_model:
            return await self.repo.get(query={'slug': slug}, projection_model=projection_model, session=session)
        return await self.repo.get(query={'slug': slug}, session=session)

    async def update_by_slug(
        self,
        slug: str,
        data: CollectionUpdateSchema,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> CollectionModel:
        obj_id = await self.update(query={'slug': slug}, data=data, session=session)

        return await self.get(query=obj_id, session=session)

    async def delete_by_slug(
        self,
        slug: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> int:
        result = await self.delete(query={'slug': slug}, session=session)
        return result

    async def get_tree(
        self,
        query: dict[str, Any] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
        children_field_name: str = 'children',
    ) -> list[ProjectionModel]:
        return await self.repo.get_tree(
            query=query, projection_model=projection_model, children_field_name=children_field_name, session=session
        )

    async def create(
        self,
        data: CollectionCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        if not isinstance(data, CollectionCreateSchema):
            data = CollectionCreateSchema.model_validate(data)

        while True:
            existing = await self.exists(query={'slug': data.slug}, session=session)
            if not existing:
                break
            data.slug = f'{data.slug.split("-")[0]}-{uuid4().hex[:8]}'

        return await super().create(data=data, session=session)

    async def get_root_collection_id(self) -> PyObjectId:
        root_collection = await self.get_by_slug(slug='root')
        return root_collection.id


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> CollectionService:
    return CollectionService(repo)
