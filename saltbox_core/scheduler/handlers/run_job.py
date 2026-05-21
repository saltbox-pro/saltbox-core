from faststream.rabbit.annotations import ContextRepo

from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobSimpleSchema
from saltbox_core.jobs.services.job_services import JobService
from saltbox_sdk.db.schemas_base import Source
from saltbox_sdk.scheduler.messages import RunTaskEventBusMessage


async def run_job_handler(message: RunTaskEventBusMessage, context: ContextRepo) -> dict:
    job_service: JobService = context.get('job_service')

    job_obj_id = await job_service.create(
        data=JobCreateSchema.model_validate(
            {
                'salt_master': message.data['salt_master'],
                'tgt': message.data['tgt'],
                'tgt_type': message.data['tgt_type'],
                'fun': message.data['fun'],
                'arg': message.data.get('arg'),
                'kwarg': message.data.get('kwarg'),
                'user': message.user,
                'source': Source(type='scheduler', id=message.task_id),
            }
        ),
        notify=True,
    )
    job = await job_service.get(query=job_obj_id, projection_model=JobSimpleSchema)

    return {'jid': job.jid}
