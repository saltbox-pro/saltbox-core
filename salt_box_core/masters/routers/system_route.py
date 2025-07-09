import logging.config
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from saltbox_bridge_messages import (
    BridgeTestBurstResponse,
    BurstJobsTestReportSchema,
    CoreTestBurstJobsRequest,
    CoreTestBurstRequest,
)

from salt_box_core.config import LOG_CONFIG, SETTINGS
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.redis.config import RedisDependency
from salt_box_core.event_bus.masters_bus import send_message_and_wait_response_to_master, send_message_to_master
from salt_box_core.http_errors import BadRequest, NotFound
from salt_box_core.jobs.services.job_services import JobServiceDependency
from salt_box_core.masters.schemas.system_schemas import (
    BurstJobsTestDeleteResponse,
    BurstJobsTestPostResponse,
    BurstJobsTestStatsResponse,
)
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from saltbox_bridge_messages import BridgeTestBurstResponse, CoreTestBurstRequest

BURST_JOBS_TEST_REPORT_HASH_NAME = 'burst_jobs_test'

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix='/system',
    tags=['System'],
    responses={status.HTTP_404_NOT_FOUND: {'description': 'Not found'}},
)


@router.get('/{user}/authorized_keys', operation_id='authorized_keys', response_class=PlainTextResponse)
async def authorized_keys(
    user: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> str:
    masters = await master_service.get_accepted_list()
    if user == SETTINGS.sshfs_user:
        attr = 'sshfs_pubkey'
    elif user == SETTINGS.salt_conf_user:
        attr = 'salt_conf_pubkey'
    else:
        msg = f'Unknown user {user}'
        raise BadRequest(msg)
    keys = [str(getattr(master, attr)) for master in masters]
    return '\n'.join(keys)


@router.post('/{master}/burst_test')
async def burst_test(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
    count: int = 100,
    size: int = 0,
) -> BridgeTestBurstResponse:
    try:
        await master_service.get_by_master_id(master_id)
    except ObjectNotFoundError:
        msg = f"Not found master_id='{master_id}'"
        raise NotFound(msg) from None
    message = CoreTestBurstRequest(master=master_id, count=count, size=size)
    # TODO (a.karmanov) : Run async, keep result in DB
    try:
        resp = await send_message_and_wait_response_to_master(message, message_tag='burst_test')
    except TimeoutError:
        msg = 'Execution is too long, try lesser count of load size or wait master to boot'
        raise BadRequest(msg) from None
    return BridgeTestBurstResponse(**resp)


@router.post('/{master}/burst_jobs_test')
async def burst_jobs_test_post(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
    duration: Annotated[int, 'Burst duration in seconds'],
    rate: Annotated[int, 'Target events rate per second'],
) -> BurstJobsTestPostResponse:
    try:
        await master_service.get_by_master_id(master_id)
    except ObjectNotFoundError:
        msg = f"Not found master_id='{master_id}'"
        raise NotFound(msg) from None

    try:
        message = CoreTestBurstJobsRequest(master=master_id, duration=timedelta(seconds=duration), rate=rate)
    except ValidationError as err:
        raise BadRequest(err.errors()) from err

    await send_message_to_master(message, message_tag='burst_jobs_test')
    return BurstJobsTestPostResponse(id=message.id)


@router.delete('/burst_jobs_test')
async def burst_jobs_test_delete(
    job_service: JobServiceDependency,
    id: Annotated[str | None, Query(description='Burst ID to delete selectively')] = None,
) -> BurstJobsTestDeleteResponse:
    deletions = await job_service.delete_fake_jobs(label=id)
    return BurstJobsTestDeleteResponse(deletions=deletions)


@router.get('/burst_jobs_test')
async def burst_jobs_test_get(
    job_service: JobServiceDependency,
    rdb: RedisDependency,
    id: Annotated[str, Query(description='Burst ID to delete selectively')],
) -> BurstJobsTestStatsResponse:
    bridge_stats_raw = await rdb.hget(name=BURST_JOBS_TEST_REPORT_HASH_NAME, key=id)
    if bridge_stats_raw is None:
        msg = f"No record for '{id}'. The burst is not completed yet?"
        raise NotFound(msg)

    bridge_stats = BurstJobsTestReportSchema.model_validate_json(bridge_stats_raw)

    count = 0
    first_dt = None
    last_dt = None
    cur = 0

    while True:
        cur, jobs = await job_service.get_fake_jobs(cursor=cur, label=id)
        count += len(jobs)
        for j in jobs:
            job_dt = j['_stamp']
            if first_dt is None or job_dt < first_dt:
                first_dt = job_dt
            if last_dt is None or job_dt > last_dt:
                last_dt = job_dt
        if cur == 0:
            break

    return BurstJobsTestStatsResponse(
        messages_sent=bridge_stats.count,
        burst_start=bridge_stats.start,
        burst_end=bridge_stats.end,
        jobs_created=count,
        first_job_time=first_dt,
        last_job_time=last_dt,
    )
