import re
from datetime import datetime
from typing import ClassVar

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnCreateSchema
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel, JobStatus
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import MessageDataType
from saltbox_core.salt.handlers.base_job_handler import BaseJobMessageHandler
from saltbox_core.tasks.tiq_tasks import process_task_job
from saltbox_sdk.db.schemas_base import SYSTEM_USER
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.utilities.helpers import format_iso8601_z, make_aware


class JobNewMessageHandler(BaseJobMessageHandler):
    """
    A message handler for new job salt message when
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'^salt/job/(?P<jid>\d{20})/new$')]
    METRIC_TAG = 'metrics:new_job'
    METRIC_TASK_TAG = 'metrics:task:new_job'
    # Mention: on salt-call call there is no salt/job/*/new event
    # (but salt/job/*/ret/* it is)

    async def normalize_data(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> MessageDataType:
        data = await super().normalize_data(match, master_id, tag, data)
        data['system_user'] = data.pop('user')
        data['salt_master'] = master_id

        raw_stamp = data.pop('_stamp')
        data['stamp'] = make_aware(datetime.fromisoformat(raw_stamp)) if raw_stamp else None

        return data

    async def get_job(self, jid: str, master_id: str, data: MessageDataType) -> JobModel:
        try:
            existed_job = await self.job_service.get(query={'jid': str(jid), 'salt_master': str(master_id)})

            return await self.job_service.update(
                query=existed_job.id,
                data={
                    'status': JobStatus.running,
                    'minions': data.get('minions', []),
                    'missing': data.get('missing', []),
                    'stamp': data.get('stamp'),
                    'system_user': data.get('system_user'),
                },
            )
        except ObjectNotFoundException:
            return await self.job_service.create(
                data=JobCreateSchema.model_validate({**data, 'status': JobStatus.running, 'user': SYSTEM_USER}),
                notify=True,
            )

    async def process(
        self,
        match: re.Match,
        master_id: str,
        data: MessageDataType,
        job: JobModel | None = None,
        tid: str | None = None,
    ) -> None:
        jid = match.group('jid')

        if tid:
            logger.info('New job (jid: %s) for task: %s', jid, tid)
        else:
            logger.info('New job: %s', jid)

        if job and job.minions:
            for minion_id in job.minions:
                await self.job_return_service.create(
                    data=JobReturnCreateSchema.model_validate(
                        {
                            'minion_id': minion_id,
                            'salt_master': master_id,
                            'jid': job.jid,
                            'fun': job.fun,
                            'source': job.source,
                            'user': job.user,
                            'stamp_job': job.stamp,
                        }
                    ),
                    notify=True,
                )

        if tid and job:
            await process_task_job.kiq(jid=jid)  # type: ignore

        raise StopProcessing()

    async def _prepare_metrics_data(
        self, match: re.Match, master_id: str, tag: str, data: MessageDataType, tid: str | None = None
    ) -> dict:
        metrics_data = await super()._prepare_metrics_data(match=match, master_id=master_id, tag=tag, data=data)
        metrics_data.update(
            {
                'jid': match.group('jid'),
                'tgt': data['tgt'],
                'fun': data['fun'],
                'stamp': format_iso8601_z(data['stamp']),
            }
        )

        if tid:
            metrics_data.update({'tid': tid})

        return metrics_data
