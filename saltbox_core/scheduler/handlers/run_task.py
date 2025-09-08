from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.common_messages import RunTaskEventBusMessage
from saltbox_core.tasks.schemas.task_schemas import TaskCreateInputSchema, TaskData
from saltbox_core.tasks.services.tasks import TaskService
from saltbox_core.tasks.services.tasks_lifespan import TaskLifespanService, get_task_lifespan_service
from saltbox_sdk.db.schemas_base import UserShort


async def run_task(message: RunTaskEventBusMessage, context: ContextRepo) -> dict:
    redis_db = context.get('redis_db')
    task_service: TaskService = context.get('task_service')
    job_service = context.get('job_service')
    minion_service = context.get('minion_service')
    collection_service = context.get('collection_service')

    task_data = message.data.get('data', {})
    task = await task_service.create(
        data=TaskCreateInputSchema.model_validate(
            {
                'user': UserShort.model_validate({'sub': 'system'}),  # TODO: get system user
                'task_template_id': message.data.get('task_template_id'),
                'fun': message.data.get('fun'),
                'salt_masters': message.data['salt_masters'],
                'data': TaskData.model_validate({'args': task_data.get('args'), 'kwargs': task_data.get('kwargs')}),
                'collection_slug': message.data['collection_slug'],
                'query': message.data.get('query'),
                'minions': message.data.get('minions'),
                'batch_size': message.data.get('batch_size'),
                'max_jobs_count_at_same_time': message.data.get('max_jobs_count_at_same_time', 1),
                'max_retries': message.data.get('max_retries', 3),
            }
        )
    )

    task_lifespan_service: TaskLifespanService = await get_task_lifespan_service(
        rdb=redis_db,
        task_service=task_service,
        job_service=job_service,
        minion_service=minion_service,
        collection_service=collection_service,
        tid=task.id,
    )
    await task_lifespan_service.run()

    return {'task_id': str(task.id)}
