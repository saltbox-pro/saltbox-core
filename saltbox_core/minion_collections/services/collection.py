from typing import Annotated, Any, ClassVar, TypeVar, overload
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from slugify import slugify

from saltbox_core.minion_collections.exceptions import (
    DuplicateChildCollectionTitleException,
    InvalidParentCollectionException,
)
from saltbox_core.minion_collections.repositories.collection import CollectionRepository, get_collection_repository
from saltbox_core.minion_collections.schemas.collection import (
    CollectionCreateSchema,
    CollectionModel,
    CollectionUpdateSchema,
)
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class CollectionService(
    MongoBaseService[CollectionRepository, CollectionModel, CollectionCreateSchema, CollectionUpdateSchema]
):
    TREE_SORT: ClassVar[dict[str, SortOrder]] = {'order': SortOrder.ASC, 'created': SortOrder.DESC}

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

    async def get_by_id_or_slug(self, collection_id: PyObjectId | None, slug: str | None) -> CollectionModel:
        if collection_id is not None:
            return await self.get(query=collection_id)

        return await self.get(query={'slug': slug})

    async def update_by_slug(
        self,
        slug: str,
        data: CollectionUpdateSchema,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> CollectionModel:
        async with get_mongo_session_with_transaction(session) as s:
            collection = await self.get_by_slug(slug=slug, session=s)
            descendants_ids = await self.repo.get_descendants_ids(target=collection.id, include_self=False, session=s)
            descendants_collections = await self.get_list(
                query={'_id': {'$in': descendants_ids}}, session=s, projection_model=CollectionModel
            )
            descendants_slugs = [descendant.slug for descendant in descendants_collections]

            if data.parent_slug == slug or data.parent_slug in descendants_slugs:
                raise InvalidParentCollectionException()

            if data.parent_slug is not None and data.parent_slug != collection.parent_slug:
                parent_collection = await self.get_by_slug(slug=data.parent_slug, session=s)
                new_parent_id: PyObjectId | None = parent_collection.id
            else:
                new_parent_id = collection.parent_id

            if new_parent_id is not None:
                siblings = await self.repo.get_children(
                    target=new_parent_id,
                    projection_model=CollectionModel,
                    session=s,
                )
                sibling_titles = {child.title for child in siblings if child.id != collection.id}
                if data.title in sibling_titles:
                    raise DuplicateChildCollectionTitleException()

            obj_id = await self.update(
                query={'slug': slug},
                data={**data.model_dump(exclude={'parent_slug'}), 'parent_id': new_parent_id},
                session=s,
            )

            return await self.get(query=obj_id, session=s)

    async def delete_by_slug(
        self,
        slug: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            return await self.delete(query={'slug': slug}, session=s)

    async def move(
        self,
        *,
        target_id: PyObjectId,
        parent_id: PyObjectId,
        insert_before_id: PyObjectId | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        async with get_mongo_session_with_transaction(session) as s:
            return await self.repo.move(
                target_id=target_id,
                parent_id=parent_id,
                insert_before_id=insert_before_id,
                session=s,
                sort=self.TREE_SORT,
            )

    async def get_tree(
        self,
        query: dict[str, Any] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
        children_field_name: str = 'children',
        sort: dict[str, SortOrder] | None = None,
    ) -> list[ProjectionModel]:
        return await self.repo.get_tree(
            query=query,
            projection_model=projection_model,
            children_field_name=children_field_name,
            session=session,
            sort=sort,
        )

    async def create(
        self,
        data: CollectionCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        if not isinstance(data, CollectionCreateSchema):
            data = CollectionCreateSchema.model_validate(data)
        async with get_mongo_session_with_transaction(session) as s:
            slug = slugify(data.title, separator='-', lowercase=True)
            while True:
                existing = await self.exists(query={'slug': slug}, session=s)
                if not existing:
                    break
                cleaned_slug = slugify(data.title, separator='-', lowercase=True)
                slug = f'{cleaned_slug}-{uuid4().hex[:8]}'

            return await super().create(data={**data.model_dump(exclude={'slug'}), 'slug': slug}, session=s)

    async def get_root_collection_id(self) -> PyObjectId:
        root_collection = await self.get_by_slug(slug='root')
        return root_collection.id


def get_collection_service(
    repo: Annotated[CollectionRepository, Depends(get_collection_repository)],
) -> CollectionService:
    return CollectionService(repo)
