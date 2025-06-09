from typing import Annotated, Any, ClassVar, overload

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.config import get_mongo
from salt_box_core.db.mongo.repository_base import ModelType
from salt_box_core.db.mongo.repository_tree_base import BaseTreeMongoRepository, OnDelete
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionBaseTreeModel, CollectionModel


class CollectionRepository(BaseTreeMongoRepository[CollectionModel]):
    class Meta(BaseTreeMongoRepository.Meta):
        collection_name = 'minion_collections'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        on_delete = OnDelete.cascade

    async def prepare_object_data(self, data: dict[str, Any]) -> dict[str, Any]:
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
            if hasattr(data, 'parent_id'):
                parent_id = data.parent_id
            else:
                parent_id = None
        else:
            parent_id = data.get('parent_id')

        if parent_id:
            try:
                await self.get(PyObjectId(parent_id))
            except ObjectNotFoundError as e:
                msg = f'Parent collection with id "{parent_id}" not found'
                raise ValueError(msg) from e

        return data


def get_collection_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> CollectionRepository:
    return CollectionRepository(db)
