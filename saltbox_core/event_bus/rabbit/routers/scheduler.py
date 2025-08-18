import json
from typing import Any

import anyio
from faststream import Context
from faststream.rabbit import RabbitRouter

from saltbox_core.event_bus.rabbit.common_messages import (
    RunTaskEventBusMessage,
    RunTaskResultEventBusMessage,
    RunTaskStatus,
    SyncTemplatesRequestEventBusMessage,
    SyncTemplatesResponseEventBusMessage,
)
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobData
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.tasks.schemas.task_schemas import TaskCreateInputSchema, TaskData
from saltbox_core.tasks.services.tasks import TaskService
from saltbox_sdk.db.schemas_base import UserShort
from saltbox_sdk.event_bus.utils import send_message

router = RabbitRouter(prefix='scheduler_')


@router.subscriber('sync_templates')
async def sync_templates(
    message: SyncTemplatesRequestEventBusMessage,
) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    templates: list[dict[str, Any]] = []

    async with (
        await anyio.Path(__file__).parent.parent.parent.joinpath('scheduler_tasks_templates.json').open('r') as f
    ):
        templates = json.loads(await f.read())

    for template in templates:
        await send_message(
            message=SyncTemplatesResponseEventBusMessage.model_validate(
                {
                    'target': 'scheduler',
                    'task_target': template.get('target', 'core'),
                    'fun': template['fun'],
                    'name': template['name'],
                    'json_schema': template.get('json_schema', {}),
                    'ui_schema': template.get('ui_schema', {}),
                }
            ),
            queue=f'{router.prefix}send_template',
        )


@router.subscriber('run_task')
async def run_task(
    message: RunTaskEventBusMessage,
    job_service: JobService = Context(),  # noqa: B008
    task_service: TaskService = Context(),  # noqa: B008
) -> None:
    if message.target is not None and message.target not in ['core', '*']:
        return

    async def _run_job() -> dict:
        job = await job_service.create(
            data=JobCreateSchema.model_validate(
                {
                    'salt_master': message.task_kwargs['salt_master'],
                    'tgt': message.task_kwargs['tgt'],
                    'tgt_type': message.task_kwargs['tgt_type'],
                    'fun': message.task_kwargs['fun'],
                    'data': JobData.model_validate(
                        {'args': message.task_kwargs['args'], 'kwargs': message.task_kwargs['kwargs']}
                    ),
                }
            )
        )

        return {'jid': job.jid}

    async def _run_task() -> dict:
        task = await task_service.create(
            data=TaskCreateInputSchema.model_validate(
                {
                    'user': UserShort.model_validate({'sub': 'system'}),  # TODO: get system user
                    'task_template_id': message.task_kwargs.get('task_template_id'),
                    'fun': message.task_kwargs.get('fun'),
                    'salt_masters': message.task_kwargs['salt_masters'],
                    'data': TaskData.model_validate(
                        {'args': message.task_kwargs['args'], 'kwargs': message.task_kwargs['kwargs']}
                    ),
                    'collection_slug': message.task_kwargs['collection_slug'],
                    'query': message.task_kwargs.get('query'),
                    'minions': message.task_kwargs.get('minions'),
                    'batch_size': message.task_kwargs.get('batch_size'),
                    'max_jobs_count_at_same_time': message.task_kwargs.get('max_jobs_count_at_same_time', 1),
                    'max_retries': message.task_kwargs.get('max_retries', 3),
                }
            )
        )
        return {'task_id': task.id}

    result_status = RunTaskStatus.FAILURE
    task_funcs = {
        'run_job': _run_job,
        'run_task': _run_task,
    }

    if 'message.fun' in task_funcs:
        try:
            result_data = await {
                'run_job': _run_job,
                'run_task': _run_task,
            }[message.fun]()

            result_status = RunTaskStatus.SUCCESS
        except Exception as e:
            result_data = {'error': str(e)}
    else:
        result_data = {'error': f'Unknown function `{message.fun}`'}

    result_message = RunTaskResultEventBusMessage(
        target='scheduler',
        process_id=message.process_id,
        status=result_status,
        data=result_data,
    )

    await send_message(message=result_message, queue=f'{router.prefix}run_task_result')
