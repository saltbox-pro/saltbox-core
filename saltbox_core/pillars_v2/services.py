from typing import Annotated, Any, overload, override

from fastapi import Depends
from pydantic import JsonValue
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.config import logger
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.pillars_v2.exceptions import PillarCreatedByRequiredException
from saltbox_core.pillars_v2.repository import PillarRepository, get_pillar_repository
from saltbox_core.pillars_v2.schemas import (
    PillarCreateSchema,
    PillarModel,
    PillarTgtType,
    PillarUpdateSchema,
)
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel


class PillarService(MongoBaseService[PillarRepository, PillarModel, PillarCreateSchema, PillarUpdateSchema]):
    def __init__(
        self,
        repo: PillarRepository,
        collection_service: CollectionService,
        minion_service: MinionService,
    ):
        super().__init__(repo=repo)
        self._collection_service = collection_service
        self._minion_service = minion_service

    @overload
    async def create(
        self,
        data: PillarCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> PillarModel: ...

    @overload
    async def create(
        self,
        data: PillarCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    @override
    async def create(
        self,
        data: PillarCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> PillarModel | ProjectionModel:
        if not isinstance(data, PillarCreateSchema):
            data = PillarCreateSchema.model_validate(data)
        if data.tgt_type == PillarTgtType.ROOT and not data.tgt_id:
            tgt_id = await self._collection_service.get_root_collection_id()
        elif data.tgt_type in (PillarTgtType.MINION, PillarTgtType.COLLECTION) and data.tgt_id:
            tgt_id = data.tgt_id
        else:
            msg = 'tgt_id is required for MINION and COLLECTION pillar types, and must be empty for ROOT type'
            raise ValueError(msg)
        if not data.created_by:
            raise PillarCreatedByRequiredException()

        data = data.model_copy(
            update={
                'tgt_id': tgt_id,
                'pillarenv': data.created_by.sub if data.is_personal else 'base',
            }
        )
        if projection_model:
            return await super().create(data=data, projection_model=projection_model, session=session)
        return await super().create(data=data, session=session)

    async def _get_merged_collection_pillars(
        self, collection_ids: list[str], pillarenv: str = 'base'
    ) -> dict[str, JsonValue]:
        logger.debug('Fetching pillars for collections: %s', collection_ids)
        collection_pillars = await self.get_list(
            query={
                'tgt_type': PillarTgtType.COLLECTION,
                'tgt_id': {'$in': [PyObjectId(cid) for cid in collection_ids]},
                'pillarenv': pillarenv,
            }
        )
        logger.debug('Collection pillars fetched: %s', collection_pillars)

        merged_pillars: dict[str, JsonValue] = {}
        # Later created pillars have higher priority
        sorted_pillars = sorted(collection_pillars, key=lambda p: p.created)
        for pillar in sorted_pillars:
            merged_pillars[pillar.name] = pillar.value
        logger.debug('Merged collection pillars: %s', merged_pillars)
        return merged_pillars

    async def _get_for_minion(
        self, minion_id: PyObjectId, collection_ids: list[str], pillarenv: str = 'base'
    ) -> dict[str, JsonValue]:
        root_pillars = await self.get_list(query={'tgt_type': PillarTgtType.ROOT, 'pillarenv': pillarenv})
        collection_pillars = await self._get_merged_collection_pillars(
            collection_ids=collection_ids, pillarenv=pillarenv
        )
        minion_pillars = await self.get_list(
            query={'tgt_type': PillarTgtType.MINION, 'tgt_id': minion_id, 'pillarenv': pillarenv}
        )

        merged_pillars: dict[str, JsonValue] = {}
        for pillar in root_pillars:
            merged_pillars[pillar.name] = pillar.value
        for name, value in collection_pillars.items():
            merged_pillars[name] = value
        for pillar in minion_pillars:
            merged_pillars[pillar.name] = pillar.value

        logger.debug('Merged pillars for minion %s: %s', minion_id, merged_pillars)
        return merged_pillars

    async def get_for_minion(self, master: str, minion_id: str, pillarenv: str = 'base') -> dict[str, JsonValue]:
        collections = await self._collection_service.get_list(query={'slug': {'$ne': 'root'}})
        minion = await self._minion_service.get_by_master_and_id(master=master, minion_id=minion_id)

        collection_queries: list[dict] = [
            {'id': c.id, 'query': {'$and': [c.query, {'_id': minion.id}]}} for c in collections
        ]

        minion_collections_ids: list[str] = []
        for pair in collection_queries:
            if await self._minion_service.exists(query=pair['query']):
                minion_collections_ids.append(pair['id'])

        return await self._get_for_minion(minion.id, minion_collections_ids, pillarenv=pillarenv)


def get_pillar_service(
    repo: Annotated[PillarRepository, Depends(get_pillar_repository)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
) -> PillarService:
    return PillarService(repo=repo, collection_service=collection_service, minion_service=minion_service)
