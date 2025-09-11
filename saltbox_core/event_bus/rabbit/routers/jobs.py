from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.common_messages import RunJobRequestEventBusMessage
from saltbox_core.jobs.services.job_services import JobService

router = RabbitRouter(prefix='jobs_')


@router.subscriber('create')
async def create(message: RunJobRequestEventBusMessage, context: ContextRepo) -> None | dict[str, str]:
    if message.target != 'core':
        return None

    job_service: JobService = context.get('job_service')

    job = await job_service.create(message.data)

    return {'jid': str(job.jid)}
