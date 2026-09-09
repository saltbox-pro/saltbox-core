from faststream import Logger
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.common_messages import RunJobRequestEventBusMessage
from saltbox_core.jobs.exceptions import JobCreateException
from saltbox_core.jobs.schemas.job_schemas import JobSimpleWithSourceSchema
from saltbox_core.jobs.services.job_services import JobService
from saltbox_sdk.db.schemas_base import Source

router = RabbitRouter(prefix='jobs_')


@router.subscriber('create')
async def create(
    message: RunJobRequestEventBusMessage, context: ContextRepo, logger: Logger
) -> None | dict[str, str | dict | Source | None]:
    if message.target != 'core':
        return None
    job_service: JobService = context.get('job_service')

    try:
        obj_id = await job_service.create(data=message.data, notify=True)
    except JobCreateException as e:
        return {'error': str(e)}

    job = await job_service.get(query=obj_id, projection_model=JobSimpleWithSourceSchema)

    return {'id': str(job.id), 'jid': str(job.jid), 'salt_master': job.salt_master, 'source': job.source}
