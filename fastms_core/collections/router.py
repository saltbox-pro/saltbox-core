import logging.config
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, Response, status

from fastms_core.collections.crud import collections_crud
from fastms_core.collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListQueryParams,
    MinionCollectionListSchema,
    MinionCollectionSchema,
    MinionCollectionUpdateSchema,
)
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


collections_router = APIRouter(prefix='/collections-old', tags=['Collections'])


@collections_router.get('', operation_id='collections_list')
async def collections_list(
    params: Annotated[MinionCollectionListQueryParams, Query()],
) -> PaginatedResponse[MinionCollectionListSchema]:
    response = await collections_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=MinionCollectionListSchema
    )
    return response


@collections_router.post('', operation_id='collection_create')
async def collection_create(item: MinionCollectionCreateSchema) -> MinionCollectionSchema:
    obj = await collections_crud.create(obj_in=item)

    return obj


@collections_router.get('/{cid}', operation_id='collection_retrieve')
async def collection_retrieve(cid: PydanticObjectId) -> MinionCollectionSchema:
    obj = await collections_crud.get(id=cid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return obj


@collections_router.put('/{cid}', operation_id='collection_update')
async def collection_update(cid: PydanticObjectId, item: MinionCollectionUpdateSchema) -> MinionCollectionSchema:
    obj = await collections_crud.get(id=cid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    obj_out = await collections_crud.update(db_obj=obj, obj_in=item)

    return obj_out


@collections_router.delete('/{cid}', operation_id='collection_delete', status_code=status.HTTP_204_NO_CONTENT)
async def collection_delete(cid: PydanticObjectId) -> Response:
    await collections_crud.remove(id=cid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
