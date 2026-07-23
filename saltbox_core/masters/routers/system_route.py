import asyncio
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis

from saltbox_bridge_messages import (
    BridgeTestBurstResponse,
    BurstJobsTestReportSchema,
    CoreEmptyMessage,
    CoreTestBurstJobsRequest,
    CoreTestBurstRequest,
)
from saltbox_core.config import SETTINGS
from saltbox_core.event_bus.redis.app import default_master_broker
from saltbox_core.event_bus.redis.masters_bus import (
    send_message_and_wait_response_to_master,
    send_message_to_master,
    send_sync_message_and_wait_response_to_master,
)
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.masters.exceptions import UnknownUserException
from saltbox_core.masters.schemas.system_schemas import (
    BurstJobsTestDeleteResponse,
    BurstJobsTestPostResponse,
    BurstJobsTestStatsResponse,
)
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.exceptions import NotFoundException

BURST_JOBS_TEST_REPORT_HASH_NAME = 'burst_jobs_test'


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
        raise UnknownUserException(msg)
    keys = [str(getattr(master, attr)) for master in masters]
    return '\n'.join(keys)


@router.post('/{master_id}/burst_test')
async def burst_test(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
    count: int = 100,
    size: int = 0,
) -> BridgeTestBurstResponse:
    await master_service.get_by_master_id(master_id)
    message = CoreTestBurstRequest(master=master_id, count=count, size=size)
    # TODO (a.karmanov) : Run async, keep result in DB
    resp = await send_message_and_wait_response_to_master(message, message_tag='burst_test')
    return BridgeTestBurstResponse(**resp)


@router.post('/{master_id}/burst_jobs_test')
async def burst_jobs_test_post(
    master_id: str,
    master_service: Annotated[MasterService, Depends(get_master_service)],
    duration: Annotated[int, 'Burst duration in seconds'],
    rate: Annotated[int, 'Target events rate per second'],
    strict: Annotated[bool, 'Interrupt when duration is over. Otherwise send all rate * duration messages'] = True,
) -> BurstJobsTestPostResponse:
    await master_service.get_by_master_id(master_id)

    message = CoreTestBurstJobsRequest(
        master=master_id,
        duration=timedelta(seconds=duration),
        rate=rate,
        strict=strict,
    )

    await send_message_to_master(message, message_tag='burst_jobs_test')
    return BurstJobsTestPostResponse(id=message.id)


@router.delete('/burst_jobs_test')
async def burst_jobs_test_delete(
    job_service: Annotated[JobService, Depends(get_job_service)],
    id: Annotated[str | None, Query(description='Burst ID to delete selectively')] = None,
) -> BurstJobsTestDeleteResponse:
    deletions = await job_service.delete_fake_jobs(label=id)
    return BurstJobsTestDeleteResponse(deletions=deletions)


@router.get('/burst_jobs_test')
async def burst_jobs_test_get(
    job_service: Annotated[JobService, Depends(get_job_service)],
    rdb: Annotated[Redis, Depends(get_redis)],
    id: Annotated[str, Query(description='Burst ID to delete selectively')],
) -> BurstJobsTestStatsResponse:
    bridge_stats_raw = await rdb.hget(name=BURST_JOBS_TEST_REPORT_HASH_NAME, key=id)
    if bridge_stats_raw is None:
        msg = f"No record for '{id}'. The burst is not completed yet?"
        raise NotFoundException(msg)

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
        messages_overdue=bridge_stats.overdue,
        burst_start=bridge_stats.start,
        burst_end=bridge_stats.end,
        jobs_created=count,
        first_job_time=first_dt,
        last_job_time=last_dt,
    )


@router.post('/ping-masters')
async def ping_master(
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> dict[str, str]:
    masters = await master_service.get_accepted_list()

    async with default_master_broker as broker:
        ping_results = await asyncio.gather(
            *[
                send_sync_message_and_wait_response_to_master(
                    message=CoreEmptyMessage(master=master.master_id),
                    message_tag='ping',
                    broker=broker,
                    response_timeout=5,
                )
                for master in masters
            ],
            return_exceptions=True,
        )
    results = {}
    for master, result in zip(masters, ping_results, strict=True):
        if isinstance(result, BaseException):
            results[master.master_id] = str(result)
        else:
            results[master.master_id] = result.get('status', 'unknown')

    return results
