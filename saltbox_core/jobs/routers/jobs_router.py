from typing import Annotated

import pydantic
from fastapi import APIRouter, Depends, Query
from pydantic import Field

from saltbox_core.config import SETTINGS
from saltbox_core.jobs.schemas.job_schemas import (
    CreateJobRequest,
    GetJobReturnResponse,
    IntJid,
    JobCreateSchema,
    JobModel,
    JobsActions,
    JobsListRequest,
    JobsListResponse,
)
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.schemas_base import PaginatedResponse, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user

# from saltbox_sdk.fastapi_utils.dependencies import get_opa_query
# from saltbox_sdk.utilities.helpers import match_query

router = APIRouter(prefix='/jobs', tags=['Jobs'])


@router.get(
    '',
    operation_id='jobs_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.list',
        action=JobsActions.LIST,
    ).model_dump(by_alias=True),
)
async def jobs_list(
    request: Annotated[JobsListRequest, Query()],
    # opa_query: Annotated[dict, Depends(get_opa_query)],
    job_service: Annotated[JobService, Depends(get_job_service)],
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
    # Apply OPA query filtering
    # filtred_data = [item for item in jobs.data if match_query(item.model_dump(), opa_query)]
    # jobs.data = filtred_data
    return jobs


@router.get(
    '/{jid}',
    operation_id='job_retrieve',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_retrieve(
    jid: IntJid,
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> JobModel:
    jid_ = JID(jid)
    return await job_service.get_job(jid_)


@router.post(
    '',
    operation_id='job_create',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.CREATE,
    ).model_dump(by_alias=True),
)
async def job_create(
    item: CreateJobRequest,
    user: Annotated[UserShort, Depends(get_current_user)],
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> JobModel:
    return await job_service.create(
        JobCreateSchema.model_validate(
            {
                'user': user.model_dump(),
                **item.model_dump(by_alias=True),
            }
        )
    )


@router.get(
    '/{jid}/returns-count',
    operation_id='job_returns_count',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_count(
    jid: IntJid,
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> Annotated[int, Field(ge=0)]:
    """
    How many return data records for job at the moment.

    To be used in pair with GET /jobs/{jid}/return cycle.
    """
    return await job_service.get_job_returns_count(JID(jid))


@router.get(
    '/{jid}/return',
    operation_id='job_returns_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_list(
    jid: IntJid,
    job_service: Annotated[JobService, Depends(get_job_service)],
    count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
    cursor: pydantic.NonNegativeInt = 0,
) -> GetJobReturnResponse:
    """
    Get list of returned by minions data.

    Amount is not guaranteed to be exactly count.
    """

    job_returns, next_cursor = await job_service.get_job_returns(jid=JID(jid), count=count, cursor=cursor)

    return GetJobReturnResponse(cursor=next_cursor, result=job_returns, length=len(job_returns))
