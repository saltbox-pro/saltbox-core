from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from salt_box_core.config import logger
from salt_box_core.db.exceptions import DuplicateKeyError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId, SkipLimitParams
from salt_box_core.schema_sync.schemas import JSONSchemaModel, JSONSchemaShortSchema, JSONSchemaSyncResponse
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
) -> JSONSchemaSyncResponse:
    try:
        return await service.sync()
    except DuplicateKeyError as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=409, detail=f'{e!s}') from e
    except TimeoutError as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=408, detail=f'{e!s}') from e
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail=f'Something went wrong...: {e!s}') from e
