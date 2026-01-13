from faststream.rabbit.annotations import ContextRepo

from saltbox_core.tasks.schemas.task import TaskCreateInputSchema
from saltbox_core.tasks.services.task import TaskService
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService
from saltbox_sdk.db.schemas_base import SYSTEM_SHORT_USER, Source
from saltbox_sdk.scheduler.messages import RunTaskEventBusMessage


async def run_task_handler(message: RunTaskEventBusMessage, context: ContextRepo) -> dict:
    redis_db = context.get('redis_db')
    task_service: TaskService = context.get('task_service')
    task_minion_service: TaskMinionService = context.get('task_minion_service')
    master_service = context.get('master_service')
    job_service = context.get('job_service')
    job_return_service = context.get('job_return_service')
    minion_service = context.get('minion_service')
    collection_service = context.get('collection_service')

    task_data = message.data.get('data', {})
    task = await task_service.create(
        data=TaskCreateInputSchema.model_validate(
            {
                'user': message.user if message.user else SYSTEM_SHORT_USER,
                'task_template_id': message.data.get('task_template_id'),
                'fun': message.data.get('fun'),
                'arg': task_data.get('arg'),
                'kwarg': task_data.get('kwarg'),
                'collection_slug': message.data.get('collection_slug'),
                'collection_id': message.data.get('collection_id'),
                'query': message.data.get('query'),
                'minions': message.data.get('minions'),
                'batch_size': message.data.get('batch_size'),
                'max_jobs_count_at_same_time': message.data.get('max_jobs_count_at_same_time', 1),
                'max_retries': message.data.get('max_retries', 3),
                'source': Source.model_validate({'type': 'scheduler', 'id': message.task_id}),
            }
        )
    )

    task_lifespan_service: TaskLifespanService = get_task_lifespan_service(
        rdb=redis_db,
        task_service=task_service,
        task_minion_service=task_minion_service,
        master_service=master_service,
        job_service=job_service,
        job_return_service=job_return_service,
        minion_service=minion_service,
        collection_service=collection_service,
        tid=task.id,
    )
    await task_lifespan_service.run()

    return {'task_id': str(task.id)}
