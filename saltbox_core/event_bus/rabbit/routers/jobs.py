from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.event_bus.rabbit.common_messages import RunJobRequestEventBusMessage
from saltbox_core.jobs.exceptions import JobCreateException
from saltbox_core.jobs.services.job_services import JobService

router = RabbitRouter(prefix='jobs_')


@router.subscriber('create')
async def create(message: RunJobRequestEventBusMessage, context: ContextRepo) -> None | dict[str, str]:
    if message.target != 'core':
        return None

    job_service: JobService = context.get('job_service')

    try:
        job = await job_service.create(data=message.data, notify=True)
    except JobCreateException as e:
        return {'error': str(e)}

    return {'jid': str(job.jid)}
