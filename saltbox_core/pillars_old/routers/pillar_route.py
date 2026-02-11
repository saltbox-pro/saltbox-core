from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile

from saltbox_core.pillars_old.schemas.pillar_schemas import (
    PillarCSVParseResult,
    PillarImportResultSchema,
    PillarImportSchema,
    PillarListQueryParams,
    PillarModel,
    PillarsActions,
    PillarSelector,
)
from saltbox_core.pillars_old.services.pillar_service import PillarService, get_pillar_service
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig

router = APIRouter(prefix='/pillars-old', tags=['Pillars Old'])


@router.get(
    '',
    operation_id='pillars_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.LIST,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillars_list(
    params: Annotated[PillarListQueryParams, Query()],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> list[PillarModel]:
    return await pillar_service.get_list(
        master_id=params.master_id, minion_id=params.minion_id, only_for_minion=params.only_for_minion
    )


@router.post(
    '',
    operation_id='pillar_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.CREATE,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_create(
    item: PillarModel,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> PillarModel:
    return await pillar_service.create(
        master_id=item.master_id, minion_id=item.minion_id, name=item.name, value=item.value, is_secure=item.is_secure
    )


@router.put(
    '',
    operation_id='pillar_update',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.UPDATE,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_update(
    item: PillarModel,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> PillarModel:
    return await pillar_service.update(
        master_id=item.master_id, minion_id=item.minion_id, name=item.name, value=item.value
    )


@router.delete(
    '',
    operation_id='pillar_delete',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.DELETE,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_delete(
    item: PillarSelector,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> None:
    await pillar_service.delete(master_id=item.master_id, minion_id=item.minion_id, name=item.name)


@router.post(
    '/parse_csv',
    operation_id='pillar_parse_csv',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.EXPORT,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_parse_csv(
    master_id: str,
    pillars_csv: UploadFile,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> list[PillarCSVParseResult]:
    return await pillar_service.parse_csv(master_id=master_id, file=pillars_csv.file)


@router.post(
    '/validate',
    operation_id='pillar_import_validate',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.VALIDATE,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_import_validate(
    data: list[PillarModel],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> list[PillarCSVParseResult]:
    return await pillar_service.validate_import_data(data)


@router.post(
    '/import',
    operation_id='pillar_import',
    openapi_extra=GatewayEndpointConfig(
        policy='core.masters.base',
        action=PillarsActions.IMPORT,
        cache_ttl=0,
    ).model_dump(by_alias=True),
)
async def pillar_import(
    data: PillarImportSchema,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
) -> PillarImportResultSchema:
    return await pillar_service.import_pillar(items=data.items, update_existing=data.update_existing)
