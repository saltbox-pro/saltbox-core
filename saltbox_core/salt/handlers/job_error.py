import re
from typing import ClassVar

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_schemas import JobStatus
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import BaseMessageHandler, MessageDataType
from saltbox_core.tasks.tiq_tasks import process_task_job_error
from saltbox_sdk.db.mongo.schemas_base import SourceWithIdOnlySchema
from saltbox_sdk.exceptions import ObjectNotFoundException


class JobErrorHandler(BaseMessageHandler):
    """
    A message handler for job error messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^saltbox/job/(?P<jid>\d{20})/error$')]

    async def process(self, match: re.Match, master_id: str, data: MessageDataType) -> None:
        jid = str(match.group('jid'))
        master_id = str(master_id)

        try:
            job = await self.job_service.get(
                query={'jid': jid, 'salt_master': master_id}, projection_model=SourceWithIdOnlySchema
            )
            tid: str | None = (
                job.source.id if job and job.source and job.source.type in ['task', 'task_system'] else None
            )

            await self.job_service.update(
                query=job.id,
                data={
                    'status': JobStatus.launch_error,
                    'launch_error_type': data.get('error_type', 'unknown'),
                },
            )

            if tid:
                await process_task_job_error.kiq(jid=jid, salt_master=master_id)  # type: ignore

        except ObjectNotFoundException:
            logger.debug(f'Job with jid "{jid}" not found on master "{master_id}"')

        raise StopProcessing()
