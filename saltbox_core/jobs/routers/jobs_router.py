from typing import Annotated

import pydantic
from fastapi import APIRouter, Depends, Query
from pydantic import Field

from saltbox_core.config import SETTINGS
from saltbox_core.jobs.schemas.job_return_schemas import GetJobReturnResponse
from saltbox_core.jobs.schemas.job_schemas import (
    CreateJobRequest,
    JobCreateSchema,
    JobModel,
    JobsActions,
    JobsListRequest,
    JobsListResponse,
    StrJid,
)
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_sdk.db.mongo.schemas_base import SortOrder
from saltbox_sdk.db.schemas_base import PaginatedResponse, Source, UserShort
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
    query = {'created': {'$gte': request.start_datetime, '$lte': request.end_datetime}}
    sort = {'created': SortOrder.DESC if request.desc else SortOrder.ASC}

    jobs = await job_service.get_list_paginated(
        query=query,
        skip=request.skip,
        limit=request.limit,
        sort=sort,
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
    jid: StrJid,
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> JobModel:
    return await job_service.get(query={'jid': jid})


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
        data=JobCreateSchema.model_validate(
            {
                'user': user.model_dump(),
                'source': Source(type='rest'),
                # 'arg': item.data.data_args if item.data else [],
                # 'kwarg': item.data.data_kwargs if item.data else {},
                **item.model_dump(by_alias=True),
            }
        ),
        notify=True,
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
    jid: StrJid,
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> Annotated[int, Field(ge=0)]:
    """
    How many return data records for job at the moment.

    To be used in pair with GET /jobs/{jid}/return cycle.
    """
    return await job_return_service.count(query={'jid': jid})


@router.get(
    '/{jid}/return',
    operation_id='job_returns_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_list(
    jid: StrJid,
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
    count: Annotated[int, Field(gt=0, lt=SETTINGS.max_count)] = 10,
    cursor: pydantic.NonNegativeInt = 0,
) -> GetJobReturnResponse:
    """
    Get list of returned by minions data.

    Amount is not guaranteed to be exactly count.
    """

    returns = await job_return_service.get_list(query={'jid': jid}, skip=cursor, limit=count)
    returns_count = len(returns)
    next_cursor = cursor + count if returns_count >= count else 0

    return GetJobReturnResponse(cursor=next_cursor, result=returns, length=returns_count)
