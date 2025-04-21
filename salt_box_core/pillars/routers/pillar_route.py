import logging.config
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.exceptions import ObjectCreateError, ObjectNotFoundError
from salt_box_core.db.schemas_base import User
from salt_box_core.dependencies import get_current_user_from_jwt
from salt_box_core.pillars.schemas.pillar_schemas import (
    PillarImportResultSchema,
    PillarImportSchema,
    PillarListQueryParams,
    PillarModel,
    PillarSelector,
)
from salt_box_core.pillars.services.pillar_service import PillarService, get_pillar_service

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/pillars',
    tags=['Pillars'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


@router.get('', operation_id='pillars_list')
async def pillars_list(
    params: Annotated[PillarListQueryParams, Query()],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
) -> list[PillarModel]:
    return await pillar_service.get_list(
        master_id=params.master_id, minion_id=params.minion_id, only_for_minion=params.only_for_minion
    )


@router.post('', operation_id='pillar_create')
async def pillar_create(
    item: PillarModel,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],
) -> PillarModel:
    try:
        pillar: PillarModel = await pillar_service.create(
            master_id=item.master_id, minion_id=item.minion_id, name=item.name, value=item.value
        )
    except (ObjectCreateError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return pillar


@router.put('', operation_id='pillar_update')
async def pillar_update(
    item: PillarModel,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],
) -> PillarModel:
    try:
        pillar: PillarModel = await pillar_service.update(
            master_id=item.master_id, minion_id=item.minion_id, name=item.name, value=item.value
        )
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return pillar


@router.delete('', operation_id='pillar_delete')
async def pillar_delete(
    item: PillarSelector,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
) -> None:
    try:
        await pillar_service.delete(master_id=item.master_id, minion_id=item.minion_id, name=item.name)
    except ObjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post('/parse_csv', operation_id='pillar_parse_csv')
async def pillar_parse_csv(
    master_id: str,
    pillars_csv: UploadFile,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
) -> list:
    return await pillar_service.parse_csv(master_id=master_id, file=pillars_csv.file)


@router.post('/import', operation_id='pillar_import')
async def pillar_import(
    data: PillarImportSchema,
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    user: Annotated[User, Depends(get_current_user_from_jwt)],  # type: ignore[unused-ignore]
) -> PillarImportResultSchema:
    return await pillar_service.import_pillar(items=data.items, update_existing=data.update_existing)
