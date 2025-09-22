from faststream.rabbit.annotations import ContextRepo

from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobData
from saltbox_core.jobs.services.job_services import JobService
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
                'data': JobData.model_validate(
                    {'args': message.data.get('args'), 'kwargs': message.data.get('kwargs')}
                ),
                'user': message.user,
            }
        )
    )

    return {'jid': job.jid}
