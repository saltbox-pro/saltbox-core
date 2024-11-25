from __future__ import annotations

import logging.config
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Query, Response, status

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.tasks.crud import tasks_crud
from fastms_core.tasks.schemas import (
    TaskTemplateCreateSchema,
    TaskTemplateListQueryParams,
    TaskTemplateListSchema,
    TaskTemplateSchema,
    TaskTemplateUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(prefix='/tasks', tags=['Task Templates'])


@router.get('', operation_id='tasks_list')
async def tasks_list(
    params: Annotated[TaskTemplateListQueryParams, Query()],
) -> PaginatedResponse[TaskTemplateListSchema]:
    response = await tasks_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=TaskTemplateListSchema
    )
    return response


@router.post('', operation_id='task_create')
async def task_create(item: TaskTemplateCreateSchema) -> TaskTemplateSchema:
    obj = await tasks_crud.create(obj_in=item)

    return TaskTemplateSchema.model_validate(obj)


@router.get('/{tid}', operation_id='task_retrieve')
async def filter_retrieve(tid: PydanticObjectId) -> TaskTemplateSchema:
    obj = await tasks_crud.get(id=tid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return TaskTemplateSchema.model_validate(obj)


@router.put('/{tid}', operation_id='task_update')
async def task_update(tid: PydanticObjectId, item: TaskTemplateUpdateSchema) -> TaskTemplateSchema:
    obj = await tasks_crud.get(id=tid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    obj_out = await tasks_crud.update(db_obj=obj, obj_in=item)

    return TaskTemplateSchema.model_validate(obj_out)


@router.delete('/{tid}', operation_id='task_delete', status_code=status.HTTP_204_NO_CONTENT)
async def task_delete(tid: PydanticObjectId) -> Response:
    await tasks_crud.remove(id=tid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
