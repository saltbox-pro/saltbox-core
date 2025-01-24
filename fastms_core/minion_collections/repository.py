import logging.config

import httpx
from fastapi import HTTPException, Request

from fastms_core.config import LOG_CONFIG, SETTINGS
from fastms_core.db.mongo.repository_base import MongoDBRepository
from fastms_core.db.mongo.schemas_base import PaginatedResponse, User
from fastms_core.minion_collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionDetailSchema,
    MinionCollectionListSchema,
    MinionCollectionSchema,
    MinionCollectionUpdateSchema,
    MinionCreateSchema,
    MinionListSchema,
    MinionSchema,
    MinionUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CollectionRepository(
    MongoDBRepository[
        MinionCollectionSchema, MinionCollectionListSchema, MinionCollectionCreateSchema, MinionCollectionUpdateSchema
    ]
):
    def __init__(self) -> None:
        super().__init__('minion_collections', MinionCollectionSchema)

    async def get_by_slug(self, slug: str) -> MinionCollectionSchema:
        client = await self.collection.find_one({'slug': slug})
        if not client:
            raise HTTPException(status_code=404, detail='Client not found')
        return self.model(**client)

    async def get_by_slug_protected(self, slug: str, user: User, request: Request) -> MinionCollectionDetailSchema:
        path_list = request.url.path.split('/')[3:]

        input_dict = {
            'input': {
                'user': user.model_dump(),
                'path': path_list,
                'method': request.method,
                'action': 'retrieve',
            }
        }
        async with httpx.AsyncClient() as r:
            response = await r.post(f'{SETTINGS.opa_url}/v1/data/core/collections', json=input_dict)
            response.raise_for_status()
            response_json = response.json()
            logger.info('response_json: %s', response_json)
            if not response_json['result'] or not response_json['result']['allow']:
                raise HTTPException(status_code=403, detail='Forbidden access')

        client = await self.get_by_slug(slug)

        return MinionCollectionDetailSchema(
            **client.model_dump(),
            allowed_actions=response_json['result']['allowed_actions'],
        )


class MinionRepository(MongoDBRepository[MinionSchema, MinionListSchema, MinionCreateSchema, MinionUpdateSchema]):
    def __init__(self) -> None:
        super().__init__('minions', MinionSchema)

    async def get_by_slug(self, slug: str) -> MinionSchema | None:
        minion = await self.collection.find_one({'slug': slug})
        if not minion:
            return None
        return self.model(**minion)

    async def get_paginated(
        self,
        search: dict | None = None,
        *,
        page: int = 0,
        per_page: int = 20,
        projection_query: dict | None = None,
    ) -> PaginatedResponse[MinionListSchema]:
        if not search:
            search = {}

        data_query = self.collection.find(search, projection_query).skip(page * per_page).limit(per_page)
        data = [MinionListSchema(**minion) async for minion in data_query]
        total = await self.collection.count_documents(search)
        logger.info('data: %s', data)
        logger.info('total: %s', total)

        return PaginatedResponse[MinionListSchema](total=total, data=data)
