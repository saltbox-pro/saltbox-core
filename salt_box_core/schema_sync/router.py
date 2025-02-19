from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from salt_box_core.config import logger
from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, SkipLimitParams
from salt_box_core.schema_sync.schemas import JSONSchemaModel, JSONSchemaShortSchema, JSONSchemaSyncResponse
from salt_box_core.schema_sync.services.schema_service import JSONSchemaService, get_json_schema_service

router = APIRouter(prefix='/json-schemas', tags=['JSON_Schemas'])


@router.get('')
async def get_json_schemas_list(
    params: Annotated[SkipLimitParams, Query()],
    service: Annotated[JSONSchemaService, Depends(get_json_schema_service)],
) -> PaginatedResponse[JSONSchemaShortSchema]:
    try:
        return await service.get_list_paginated(
            query=None, skip=params.skip, limit=params.limit, projection_model=JSONSchemaShortSchema
        )
    except Exception as e:
        logger.error('Error: %s', e)
        raise HTTPException(status_code=500, detail='Something went wrong... See logs') from e


@router.get('/{name}')
async def get_json_schema(
    name: str,
    service: Annotated[JSONSchemaService, Depends(get_json_schema_service)],
) -> JSONSchemaModel:
    if await service.exists({'name': name}):
        return await service.get_by_name(name)
    # Try get default schema
    try:
        return await service.get_by_name('default')
    except ObjectNotFoundError:
        msg = f'Schema with name `{name}` not found. Default schema also not found: check schema repository'
        logger.error(msg)
        raise HTTPException(status_code=404, detail=msg) from None


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
