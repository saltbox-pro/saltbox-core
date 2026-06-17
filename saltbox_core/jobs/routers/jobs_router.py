import csv
import io
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import Response
from pydantic import Field

from saltbox_core.jobs.schemas.job_return_schemas import (
    JobReturnDataListPaginatedResponse,
    JobReturnDataOnlyScheme,
    JobReturnListResponse,
    JobReturnsDataCSVBody,
    JobReturnsListBody,
    JobReturnStatus,
)
from saltbox_core.jobs.schemas.job_schemas import (
    CreateJobRequest,
    JobCreateSchema,
    JobListBody,
    JobModel,
    JobsActions,
    JobsListResponse,
    StrJid,
)
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.db.schemas_base import PaginatedResponse, Source, UserShort
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig
from saltbox_sdk.fastapi_utils.dependencies import get_current_user, get_opa_query

router = APIRouter(prefix='/jobs', tags=['Jobs'])


@router.post(
    '/list',
    operation_id='jobs_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.list',
        action=JobsActions.LIST,
    ).model_dump(by_alias=True),
)
async def jobs_list(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    body: Annotated[JobListBody, Body()],
    job_service: Annotated[JobService, Depends(get_job_service)],
) -> PaginatedResponse[JobsListResponse]:
    query = body.query

    if opa_query:
        query = {'$and': [query, opa_query]}

    jobs = await job_service.get_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        projection_model=JobsListResponse,
        sort=body.sort,
    )

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
    job_obj_id = await job_service.create(
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
    return await job_service.get(query=job_obj_id)


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


@router.post(
    '/returns/list',
    operation_id='job_returns_list',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_list(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    body: Annotated[JobReturnsListBody, Body()],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> PaginatedResponse[JobReturnListResponse]:
    query = body.query

    if opa_query:
        query = {'$and': [query, opa_query]}

    job_returns = await job_return_service.get_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        projection_model=JobReturnListResponse,
        sort=body.sort,
    )

    return job_returns


@router.post(
    '/returns/table',
    operation_id='job_returns_table',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_table(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    body: Annotated[JobReturnsListBody, Body()],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> JobReturnDataListPaginatedResponse:
    base_query = {'status': JobReturnStatus.success}
    sort = body.sort

    query: dict[str, Any]
    if body.query:
        query = {'$and': [base_query, body.query]}
    else:
        query = base_query

    if opa_query:
        query = {'$and': [query, opa_query]}

    if not sort:
        sort = {'minion_id': SortOrder.ASC}

    data_table = await job_return_service.get_data_list_paginated(
        query=query,
        skip=body.skip,
        limit=body.limit,
        sort=sort,
    )

    return data_table


@router.post(
    '/returns/csv',
    operation_id='job_returns_csv',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_returns_csv(
    opa_query: Annotated[dict, Depends(get_opa_query)],
    body: Annotated[JobReturnsDataCSVBody, Body()],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> Response:
    base_query = {'status': JobReturnStatus.success}
    sort = body.sort

    query: dict[str, Any]
    if body.query:
        query = {'$and': [base_query, body.query]}
    else:
        query = base_query

    if opa_query:
        query = {'$and': [query, opa_query]}

    if not sort:
        sort = {'minion_id': SortOrder.ASC}

    data = await job_return_service.get_data_list(
        query=query,
        sort=sort,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(data.columns)
    for item in data.data:
        writer.writerow([item.get(column_name) for column_name in data.columns])

    return Response(
        content=buffer.getvalue(),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="job_returns_data.csv"'},
    )


@router.get(
    '/returns/data',
    operation_id='job_return_data',
    openapi_extra=GatewayEndpointConfig(
        policy='core.jobs.base',
        action=JobsActions.READ,
    ).model_dump(by_alias=True),
)
async def job_return_data(
    job_return_mongo_id: PyObjectId,
    opa_query: Annotated[dict, Depends(get_opa_query)],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
) -> Any:
    query: dict[str, Any] = {'_id': job_return_mongo_id}

    if opa_query:
        query = {'$and': [query, opa_query]}

    job_return = await job_return_service.get(
        query=query,
        projection_model=JobReturnDataOnlyScheme,
    )

    return job_return.data
