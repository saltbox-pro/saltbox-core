from typing import Annotated, Any, ClassVar, overload

import pymongo
from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import logger
from saltbox_core.minion_collections.exceptions import (
    CyclicCollectionReferenceException,
    ReferencedCollectionDeleteException,
    UnknownCollectionReferenceException,
)
from saltbox_core.minion_collections.schemas.collection import (
    CollectionBaseTreeModel,
    CollectionCreateSchema,
    CollectionModel,
)
from saltbox_core.minion_collections.utils.collection_filter import find_cycle, get_referenced_slugs
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
        order_field_name = 'order'
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'slug_unique_index_asc': [('slug', pymongo.ASCENDING)],
            'parent_id_title_unique_index_asc': [('parent_id', pymongo.ASCENDING), ('title', pymongo.ASCENDING)],
            'parent_id_order_created_index': [
                ('parent_id', pymongo.ASCENDING),
                ('order', pymongo.ASCENDING),
                ('created', pymongo.DESCENDING),
            ],
        }

    async def prepare_object_data(
        self,
        data: dict[str, Any],
        projection_model: type[ProjectionModel] | None = None,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> dict[str, Any]:
        fields_to_get_parent = ['full_query', 'parent_slug', 'parent_title']

        if projection_model is None or any(
            field_name in fields_to_get_parent for field_name in projection_model.model_fields.keys()
        ):
            parent = await self.get_parent(
                PyObjectId(data['_id']), projection_model=CollectionBaseTreeModel, session=session
            )
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
    async def validate_object_data(
        self,
        data: ModelType,
        *,
        query: dict[str, Any] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> ModelType: ...

    @overload
    async def validate_object_data(
        self,
        data: dict[str, Any],
        *,
        query: dict[str, Any] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> dict[str, Any]: ...

    async def validate_object_data(
        self,
        data: ModelType | dict[str, Any],
        *,
        query: dict[str, Any] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> ModelType | dict[str, Any]:
        is_parent_set, raw_parent_id = self._get_data_field(data, 'parent_id', is_creation=query is None)
        is_query_set, collection_query = self._get_data_field(data, 'query', is_creation=query is None)
        parent_id = PyObjectId(str(raw_parent_id)) if raw_parent_id is not None else None

        if parent_id:
            try:
                await self.get(parent_id, session=session)
            except ObjectNotFoundException:
                msg = f'Parent collection with id "{parent_id}" not found'
                raise ObjectNotFoundException(msg) from None

        if is_query_set:
            await self._validate_referenced_slugs_exist(collection_query, session=session)

        if query is not None and (is_parent_set or is_query_set):
            targets = await self.collection.find(
                filter=query, projection={'_id': 1, 'parent_id': 1, 'query': 1}, session=session
            ).to_list()

            for target in targets:
                await self._validate_no_reference_cycle(
                    PyObjectId(target['_id']),
                    parent_id=parent_id if is_parent_set else target.get('parent_id'),
                    query=collection_query if is_query_set else target.get('query'),
                    session=session,
                )

        return data

    async def validate_move(
        self,
        target_id: PyObjectId,
        parent_id: PyObjectId | None,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        target = await self.collection.find_one(filter={'_id': target_id}, projection={'query': 1}, session=session)
        await self._validate_no_reference_cycle(
            target_id, parent_id=parent_id, query=(target or {}).get('query'), session=session
        )

    async def validate_delete(
        self,
        ids: list[PyObjectId],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        collections = await self.collection.find(
            filter={}, projection={'_id': 1, 'slug': 1, 'query': 1}, session=session
        ).to_list()
        deleted_slugs = {collection['slug'] for collection in collections if collection['_id'] in ids}
        referencing_slugs = [
            collection['slug']
            for collection in collections
            if collection['_id'] not in ids and get_referenced_slugs(collection.get('query')) & deleted_slugs
        ]

        if referencing_slugs:
            raise ReferencedCollectionDeleteException(sorted(referencing_slugs))

    @staticmethod
    def _get_data_field(data: BaseModel | dict[str, Any], field_name: str, *, is_creation: bool) -> tuple[bool, Any]:
        if isinstance(data, BaseModel):
            is_set = field_name in type(data).model_fields and (is_creation or field_name in data.model_fields_set)
            return is_set, getattr(data, field_name, None)

        return field_name in data, data.get(field_name)

    async def _validate_referenced_slugs_exist(
        self, collection_query: Any, *, session: MongoAsyncClientSession | None = None
    ) -> None:
        referenced_slugs = get_referenced_slugs(collection_query)
        if not referenced_slugs:
            return

        existing = await self.collection.find(
            filter={'slug': {'$in': list(referenced_slugs)}}, projection={'slug': 1}, session=session
        ).to_list()
        unknown_slugs = referenced_slugs - {collection['slug'] for collection in existing}

        if unknown_slugs:
            raise UnknownCollectionReferenceException(sorted(unknown_slugs))

    async def _validate_no_reference_cycle(
        self,
        target_id: PyObjectId,
        *,
        parent_id: PyObjectId | None,
        query: Any,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        collections = await self.collection.find(
            filter={}, projection={'_id': 1, 'slug': 1, 'parent_id': 1, 'query': 1}, session=session
        ).to_list()
        nodes = {PyObjectId(collection['_id']): collection for collection in collections}
        nodes[target_id] = {**nodes.get(target_id, {}), 'parent_id': parent_id, 'query': query}
        ids_by_slug = {node['slug']: node_id for node_id, node in nodes.items() if node.get('slug')}

        edges: dict[PyObjectId, set[PyObjectId]] = {}
        for node_id, node in nodes.items():
            dependencies = {
                ids_by_slug[slug] for slug in get_referenced_slugs(node.get('query')) if slug in ids_by_slug
            }
            if node.get('parent_id') is not None:
                dependencies.add(PyObjectId(node['parent_id']))
            edges[node_id] = dependencies

        if cycle := find_cycle(target_id, edges):
            raise CyclicCollectionReferenceException([nodes[node_id].get('slug') or str(node_id) for node_id in cycle])

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
