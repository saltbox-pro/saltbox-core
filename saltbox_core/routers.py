from fastapi import APIRouter

from saltbox_core.db.schemas_base import TaskiqTaskResult
from saltbox_core.tkq import broker
from saltbox_sdk.config.discovery_config import DISCOVERY_SETTINGS
from saltbox_sdk.discovery_client.schemas import GatewayEndpointConfig, HealthCheckResponse

router = APIRouter(prefix='', tags=['Utils'])


@router.get('/discovery/health')
async def health_check() -> HealthCheckResponse:
    """Health check endpoint"""
    return HealthCheckResponse(
        status='ok',
        message=f'Instance of {DISCOVERY_SETTINGS.service_name} is running',
    )


@router.get(
    '/bg-task-result/{task_id}',
    operation_id='read_bg_task_result',
    openapi_extra=GatewayEndpointConfig(
        policy='public',
        action='read_bg_task_result',
    ).model_dump(by_alias=True),
)
async def get_sync_status(task_id: str) -> TaskiqTaskResult:
    """
    Get task status by task_id.
    """
    progress = await broker.result_backend.get_progress(task_id)

    is_ready = await broker.result_backend.is_result_ready(task_id)
    if is_ready:
        result = await broker.result_backend.get_result(task_id)

        response = TaskiqTaskResult(
            task_id=task_id,
            progress=progress.state if progress else None,
            progress_meta=progress.meta if progress else None,
            return_value=result.return_value,
            is_err=result.is_err,
            execution_time=result.execution_time,
            log=result.log,
            error=result.error,
        )
    else:
        response = TaskiqTaskResult(
            task_id=task_id,
            progress=progress.state if progress else None,
            progress_meta=progress.meta if progress else None,
            return_value=None,
            is_err=False,
            execution_time=0,
            log='',
            error=None,
        )
    return response
