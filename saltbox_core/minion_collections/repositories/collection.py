from typing import Annotated, Any, ClassVar, overload

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.collection import (
    CollectionBaseTreeModel,
    CollectionCreateSchema,
    CollectionModel,
)
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import ModelType, ProjectionModel
from saltbox_sdk.db.mongo.repository_tree_base import BaseTreeMongoRepository, OnDelete
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException


class CollectionRepository(BaseTreeMongoRepository[CollectionModel]):
    class Meta(BaseTreeMongoRepository.Meta):
        collection_name = 'minion_collections'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        on_delete = OnDelete.cascade
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'slug_unique_index_asc': [('slug', pymongo.ASCENDING)],
            'parent_id_title_unique_index_asc': [('parent_id', pymongo.ASCENDING), ('title', pymongo.ASCENDING)],
        }

    async def prepare_object_data(
        self, data: dict[str, Any], projection_model: type[ProjectionModel] | None = None
    ) -> dict[str, Any]:
        fields_to_get_parent = ['full_query', 'parent_slug', 'parent_title']

        if projection_model is None or any(
            field_name in fields_to_get_parent for field_name in projection_model.model_fields.keys()
        ):
            parent = await self.get_parent(PyObjectId(data['_id']), projection_model=CollectionBaseTreeModel)
            query = data['query'] if 'query' in data else {}

            if parent and parent.full_query and query:
                data['full_query'] = {'$and': [parent.full_query, query]}
            elif parent and parent.full_query and not query:
                data['full_query'] = parent.full_query
            else:
                data['full_query'] = query

            data['parent_slug'] = parent.slug if parent else None
            data['parent_title'] = parent.title if parent else None

        return data

    @overload
    async def validate_object_data(self, data: ModelType) -> ModelType: ...

    @overload
    async def validate_object_data(self, data: dict[str, Any]) -> dict[str, Any]: ...

    async def validate_object_data(self, data: ModelType | dict[str, Any]) -> ModelType | dict[str, Any]:
        if isinstance(data, BaseModel):
            raw = getattr(data, 'parent_id', None)
        else:
            raw = data.get('parent_id')

        parent_id = str(raw) if raw is not None else None

        if parent_id:
            try:
                await self.get(PyObjectId(parent_id))
            except ObjectNotFoundException:
                msg = f'Parent collection with id "{parent_id}" not found'
                raise ObjectNotFoundException(msg) from None

        return data

    async def _post_create_collection(self) -> None:
        is_exist = bool(await self.collection.count_documents(filter={'slug': 'root'}))
        if not is_exist:
            msg = f"{self.__class__.__name__} doesn't exist... Creating..."
            logger.debug(msg)

            obj = CollectionCreateSchema(
                title='Root collection',
                slug='root',
                query={},
                owner_id='system',
            )
            _ = await self.create(obj)
            msg = f'{self.__class__.__name__} with `{obj.slug}` slug created'
            logger.debug(msg)
        else:
            logger.debug('Root collection already exists')


def get_collection_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> CollectionRepository:
    return CollectionRepository(db)
