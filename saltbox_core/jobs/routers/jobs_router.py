from typing import Annotated

import pydantic
from fastapi import APIRouter, Query
from pydantic import Field

from saltbox_bridge_messages import BridgeNewJobResponse, CoreNewJobRequest
from saltbox_core.config import SETTINGS
from saltbox_core.event_bus.masters_bus import send_message_and_wait_response_to_master
from saltbox_core.jobs.schemas.job_schemas import (
    CreateJobRequest,
    GetJobReturnResponse,
    IntJid,
    JobCreateSchema,
    JobModel,
    JobsListCursorRequest,
    JobsListRequest,
    JobsListResponse,
    JobSyncResponse,
)
from saltbox_core.jobs.services.job_services import JobServiceDependency
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.schemas_base import CursoredResponse, PaginatedResponse

router = APIRouter(
    prefix='/jobs',
    tags=['Jobs'],
    responses={404: {'description': 'Not found'}},
)

ws_router = APIRouter(prefix='/jobs')


@router.get('/cursored_list', operation_id='jobs_list_cursor')
async def jobs_list_cursor(
    request: Annotated[JobsListCursorRequest, Query()],
    job_service: JobServiceDependency,
) -> CursoredResponse[JobsListResponse]:
    matches = []

    if request.fun:
        matches.append(f'"fun": "{request.fun}"')

    if request.minion:
        matches.append(rf'"minions": \[*"{request.minion}"*\]')

    return await job_service.get_list_cursored_by_dt(
        start_datetime=request.start_datetime,
        end_datetime=request.end_datetime,
        cursor=request.cursor or 0,
        count=request.count,
        match='*' + '*'.join(matches) + '*',
        projection_model=JobsListResponse,
    )


@router.get('', operation_id='jobs_list')
async def jobs_list(
    request: Annotated[JobsListRequest, Query()],
    job_service: JobServiceDependency,
) -> PaginatedResponse[JobsListResponse]:
    start_datetime = request.start_datetime if not request.desc else request.end_datetime
    end_datetime = request.end_datetime if not request.desc else request.start_datetime
    jobs = await job_service.get_list_by_dt_paginated(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        skip=request.skip,
        limit=request.limit,
        desc=request.desc,
        projection_model=JobsListResponse,
    )
    return jobs


@router.get('/{jid}', operation_id='job_retrieve')
async def job_retrieve(
    jid: IntJid,
    job_service: JobServiceDependency,
) -> JobModel:
    _jid = JID(jid)
    return await job_service.get_job(_jid)


@router.post('', operation_id='job_create')
async def job_create(
    item: CreateJobRequest,
    job_service: JobServiceDependency,
) -> JobModel:
    return await job_service.create(
        JobCreateSchema.model_validate(
            {
                **item.model_dump(by_alias=True),
            }
        )
    )


@router.post('/sync_run', operation_id='job_create_sync')
async def job_create_sync(
    item: CreateJobRequest,
) -> JobSyncResponse:
    msg = CoreNewJobRequest(
        tgt=item.tgt,
        tgt_type=item.tgt_type,
        fun=item.fun,
        master=item.salt_master,
        arg=item.data.data_args or [] if item.data else [],
        kwarg=item.data.data_kwargs or {} if item.data else {},
    )
    job_res = BridgeNewJobResponse(
        **await send_message_and_wait_response_to_master(
            message=msg,
            message_tag='run_job_sync',
            response_timeout=10.0,
        )
    )

    return JobSyncResponse(**job_res.model_dump())


@router.get('/{jid}/returns-count', operation_id='job_returns_count')
async def job_returns_count(
    jid: IntJid,
    job_service: JobServiceDependency,
) -> Annotated[int, Field(ge=0)]:
    """
    How many return data records for job at the moment.

    To be used in pair with GET /jobs/{jid}/return cycle.
    """
    return await job_service.get_job_returns_count(JID(jid))


@router.get('/{jid}/return', operation_id='job_returns_list')
async def job_returns_list(
    jid: IntJid,
    job_service: JobServiceDependency,
    count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
    cursor: pydantic.NonNegativeInt = 0,
) -> GetJobReturnResponse:
    """
    Get list of returned by minions data.

    Amount is not guaranteed to be exactly count.
    """

    job_returns, next_cursor = await job_service.get_job_returns(jid=JID(jid), count=count, cursor=cursor)

    return GetJobReturnResponse(cursor=next_cursor, result=job_returns, length=len(job_returns))
