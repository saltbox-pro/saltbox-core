from typing import Annotated, Any

from taskiq import TaskiqDepends

from saltbox_core.jobs.schemas.job_return_schemas import JobReturnForTaskStatusUpdate
from saltbox_core.jobs.schemas.job_schemas import JobForTaskStatusUpdateSchema
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.tasks.schemas.task import TaskForStatusUpdateSchema
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionForTaskStatusUpdateSchema, TaskMinionStatus
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.tkq import broker, queue_default
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.utilities.helpers import utc_now


@broker.task(queue_name=queue_default.name)
async def process_task_job_return(
    jid: str,
    minion_id: str,
    job_return_service: Annotated[JobReturnService, TaskiqDepends(get_job_return_service)],
    task_service: Annotated[TaskService, TaskiqDepends(get_task_service)],
    task_minion_service: Annotated[TaskMinionService, TaskiqDepends(get_task_minion_service)],
) -> None:
    job_return = await job_return_service.get(
        query={'jid': jid, 'minion_id': minion_id}, projection_model=JobReturnForTaskStatusUpdate
    )

    if job_return.source and job_return.source.type == 'task' and job_return.source.id:
        task = await task_service.get(
            query=PyObjectId(job_return.source.id), projection_model=TaskForStatusUpdateSchema
        )
        task_minion = await task_minion_service.get(
            query={'task_id': task.id, 'minion_id': minion_id, 'master': job_return.salt_master},
            projection_model=TaskMinionForTaskStatusUpdateSchema,
        )
        is_success = job_return.retcode == 0

        data_to_update: dict[str, Any] = {}

        if is_success:
            data_to_update['status'] = TaskMinionStatus.success
            data_to_update['finished_dt'] = utc_now()
        else:
            if task_minion.count_runs >= task.max_retries:
                data_to_update['status'] = TaskMinionStatus.failed
                data_to_update['finished_dt'] = utc_now()
            else:
                data_to_update['status'] = TaskMinionStatus.pending

        await task_minion_service.update(query=task_minion.id, data=data_to_update)


@broker.task(queue_name=queue_default.name)
async def process_task_job_error(
    jid: str,
    job_service: Annotated[JobService, TaskiqDepends(get_job_service)],
    task_service: Annotated[TaskService, TaskiqDepends(get_task_service)],
    task_minion_service: Annotated[TaskMinionService, TaskiqDepends(get_task_minion_service)],
) -> None:
    job = await job_service.get(query={'jid': jid}, projection_model=JobForTaskStatusUpdateSchema)

    if job.source and job.source.type in ['task', 'task_system'] and job.source.id:
        task = await task_service.get(query=PyObjectId(job.source.id), projection_model=EmptyModel)
        minions_ids = job.tgt if isinstance(job.tgt, list) else [job.tgt]

        await task_minion_service.bulk_update(
            query={'task_id': task.id, 'minion_id': {'$in': minions_ids}, 'master': job.salt_master},
            data={'status': TaskMinionStatus.failed},
        )
