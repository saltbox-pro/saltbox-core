import logging.config
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, HTTPException, Query, Response, status

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.schemas_base import PaginatedResponse
from fastms_core.tasks.crud import task_crud, task_template_crud
from fastms_core.tasks.models import Task, TaskTemplate
from fastms_core.tasks.schemas import (
    TaskListQueryParams,
    TaskListSchema,
    TaskTemplateCreateSchema,
    TaskTemplateListQueryParams,
    TaskTemplateListSchema,
    TaskTemplateSchema,
    TaskTemplateUpdateSchema,
)

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/tasks',
    tags=['Tasks'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


# Task templates views


@router.get('/template', operation_id='templates_list')
async def templates_list(
    params: Annotated[TaskTemplateListQueryParams, Query()],
) -> PaginatedResponse[TaskTemplateListSchema]:
    response = await task_template_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=TaskTemplateListSchema
    )
    return response


@router.post('/template', operation_id='template_create')
async def template_create(item: TaskTemplateCreateSchema) -> TaskTemplateSchema:
    obj = await task_template_crud.create(obj_in=item)

    return TaskTemplateSchema.model_validate(obj)


@router.get('/template/{tid}', operation_id='template_retrieve')
async def template_retrieve(tid: PydanticObjectId) -> TaskTemplate:
    obj = await task_template_crud.get(id=tid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    print(obj.create_task({'test_arg': 'test_arg value 123'}))

    return TaskTemplate.model_validate(obj)


@router.put('/template/{tid}', operation_id='template_update')
async def template_update(tid: PydanticObjectId, item: TaskTemplateUpdateSchema) -> TaskTemplateSchema:
    obj = await task_template_crud.get(id=tid)

    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    obj_out = await task_template_crud.update(db_obj=obj, obj_in=item)

    return TaskTemplateSchema.model_validate(obj_out)


@router.delete('/template/{tid}', operation_id='template_delete', status_code=status.HTTP_204_NO_CONTENT)
async def template_delete(tid: PydanticObjectId) -> Response:
    await task_template_crud.remove(id=tid)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Tasks views


@router.post('', operation_id='tasks_list')
async def tasks_list(
    params: Annotated[TaskListQueryParams, Body()],
) -> PaginatedResponse[TaskListSchema]:
    response = await task_crud.get_paginated(
        page=params.page, per_page=params.per_page, projection_model=TaskListSchema
    )

    return response


@router.get('/{tid}', operation_id='task_retrieve')
async def task_retrieve(tid: PydanticObjectId) -> Task:
    task = await task_crud.get(tid)

    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')

    return task
