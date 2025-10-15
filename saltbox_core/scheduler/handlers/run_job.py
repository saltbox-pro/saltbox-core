from faststream.rabbit.annotations import ContextRepo

from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema
from saltbox_core.jobs.services.job_services import JobService
from saltbox_sdk.db.schemas_base import Source
from saltbox_sdk.scheduler.messages import RunTaskEventBusMessage


async def run_job(message: RunTaskEventBusMessage, context: ContextRepo) -> dict:
    job_service: JobService = context.get('job_service')

    job = await job_service.create(
        data=JobCreateSchema.model_validate(
            {
                'salt_master': message.data['salt_master'],
                'tgt': message.data['tgt'],
                'tgt_type': message.data['tgt_type'],
                'fun': message.data['fun'],
                'arg': message.data.get('args'),
                'kwarg': message.data.get('kwargs'),
                'user': message.user,
                'source': Source(type='scheduler', id=message.task_id),
            }
        ),
        notify=True,
    )

    return {'jid': job.jid}
