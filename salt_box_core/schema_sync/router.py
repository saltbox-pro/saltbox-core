from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from salt_box_core.config import logger
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId, SkipLimitParams
from salt_box_core.schema_sync.schemas import JSONSchemaModel, JSONSchemaShortSchema
from salt_box_core.schema_sync.services.schema_service import JSONSchemaService, get_json_schema_service

router = APIRouter(prefix='/json-schemas', tags=['JSON Schemas'])


@router.get('')
async def get_json_schemas_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[JSONSchemaService, Depends(get_json_schema_service)],
) -> PaginatedResponse[JSONSchemaShortSchema]:
    try:
        return await service.get_list_paginated(skip=params.skip, limit=params.limit)
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/{sid}')
async def get_json_schema(
    sid: PyObjectId,
    service: Annotated[JSONSchemaService, Depends(get_json_schema_service)],
) -> JSONSchemaModel:
    return await service.get(sid)


@router.post('/sync')
async def sync_schemas(
    service: Annotated[JSONSchemaService, Depends(get_json_schema_service)],
) -> dict:
    try:
        return await service.sync()
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e
