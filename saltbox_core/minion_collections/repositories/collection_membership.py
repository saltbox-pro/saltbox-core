from datetime import datetime
from typing import Annotated, Any, ClassVar

import pymongo
from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.minion_collections.schemas.collection_membership import CollectionMembershipModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class CollectionMembershipRepository(BaseMongoRepository[CollectionMembershipModel]):
    async def get_active_minion_ids(
        self, collection_id: PyObjectId, *, session: AsyncClientSession | None = None
    ) -> set[PyObjectId]:
        docs = await self.collection.find(
            {'collection_id': collection_id, 'exited_at': None},
            {'minion_inner_id': 1, '_id': 0},
            session=session,
        ).to_list()
        return {doc['minion_inner_id'] for doc in docs}

    async def get_active_collection_ids(self) -> list[PyObjectId]:
        return await self.collection.distinct('collection_id', {'exited_at': None})

    async def get_minion_collection_ids(self, minion_inner_id: PyObjectId) -> list[PyObjectId]:
        docs = await self.collection.find(
            {'minion_inner_id': minion_inner_id, 'exited_at': None},
            {'collection_id': 1, '_id': 0},
        ).to_list()
        return [doc['collection_id'] for doc in docs]

    async def close_intervals(
        self,
        collection_id: PyObjectId,
        minion_ids: list[PyObjectId],
        exited_at: datetime,
        *,
        session: AsyncClientSession | None = None,
    ) -> None:
        await self.collection.update_many(
            {'collection_id': collection_id, 'minion_inner_id': {'$in': minion_ids}, 'exited_at': None},
            {'$set': {'exited_at': exited_at}},
            session=session,
        )

    class Meta:
        collection_name = 'minion_collection_memberships'
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'active_membership_unique_index': [
                ('collection_id', pymongo.ASCENDING),
                ('minion_inner_id', pymongo.ASCENDING),
            ],
            'minion_membership_index': [
                ('minion_inner_id', pymongo.ASCENDING),
                ('exited_at', pymongo.ASCENDING),
                ('collection_id', pymongo.ASCENDING),
            ],
        }
        collection_index_options: ClassVar[dict[str, dict[str, Any]]] = {
            'active_membership_unique_index': {
                'unique': True,
                'partialFilterExpression': {'exited_at': None},
            },
        }


def get_collection_membership_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)],
) -> CollectionMembershipRepository:
    return CollectionMembershipRepository(db)
