import json
import re
from datetime import datetime
from typing import Any, ClassVar

import redis.asyncio as aioredis
from faststream.rabbit import RabbitBroker

from saltbox_core.config import SETTINGS, logger
from saltbox_core.event_bus.rabbit.common_messages import InventoryPutEventBusMessage, InventoryPutForMinion
from saltbox_core.jobs.schemas.job_return_schemas import (
    JobReturnCreateSchema,
    JobReturnModel,
    JobReturnStatus,
    JobReturnUpdateSchema,
)
from saltbox_core.jobs.schemas.job_schemas import JobModel
from saltbox_core.jobs.services.job_return_service import JobReturnService
from saltbox_core.jobs.services.job_services import JobService
from saltbox_core.minion_collections.services.minion_service import MinionService
from saltbox_core.salt.exceptions import StopProcessing
from saltbox_core.salt.handlers.base_handler import MessageDataType
from saltbox_core.salt.handlers.base_job_handler import BaseJobMessageHandler
from saltbox_core.tasks.tiq_tasks import process_task_job_return
from saltbox_core.utilities.jid import JID
from saltbox_sdk.event_bus.utils import send_message
from saltbox_sdk.exceptions import DuplicateKeyException, NotFoundException
from saltbox_sdk.utilities.helpers import format_iso8601_z, make_aware


class JobReturnMessageHandler(BaseJobMessageHandler):
    """
    A message handler that handles salt job return messages
    """

    tag_patterns: ClassVar[list[re.Pattern[str]]] = [re.compile(r'salt/job/(?P<jid>\d{20})/ret/(?P<mid>.+)')]
    METRIC_TAG = 'metrics:job_return'
    METRIC_TASK_TAG = 'metrics:task:job_return'
    INVENTORY_SAVED_MSG_TAG = 'inventory_saved'
    INVENTORY_STATE = 'inventory'

    _STATUS_SUCCESS = 'success'
    _STATUS_PARTIAL_SUCCESS = 'partial_success'
    _STATUS_FAILED = 'failed'

    def __init__(
        self,
        redis_client: aioredis.Redis,
        job_service: JobService,
        job_return_service: JobReturnService,
        minion_service: MinionService,
        broker: RabbitBroker,
    ) -> None:
        super().__init__(redis_client=redis_client, job_service=job_service, job_return_service=job_return_service)

        self.minion_service = minion_service
        self.broker = broker

    async def normalize_data(self, match: re.Match, master_id: str, tag: str, data: MessageDataType) -> MessageDataType:

        normalized_data = await super().normalize_data(match=match, master_id=master_id, tag=tag, data=data)

        system_user = normalized_data.pop('user', 'undefined')  # NOTE: KeyError - field `user` in 3005.1 does not exist
        minion_id = normalized_data.pop('id', match.group('mid'))
        salt_master = normalized_data.pop('master_id', master_id)

        enriched_data = {
            **normalized_data,
            'user': system_user,  # NOTE: field `user` in 3005.1 does not exist
            'system_user': system_user,
            'minion_id': minion_id,
            'salt_master': salt_master,
        }

        if enriched_data.get('retcode', None) == 0:
            enriched_data['status'] = JobReturnStatus.success
        else:
            enriched_data['status'] = JobReturnStatus.failed

        raw_stamp = enriched_data.pop('_stamp')
        iso_stamp = datetime.fromisoformat(raw_stamp)
        enriched_data['stamp'] = make_aware(iso_stamp) if raw_stamp else None

        return enriched_data

    async def get_job(self, jid: str, master_id: str, data: MessageDataType) -> JobModel:
        return await self.job_service.get(query={'jid': str(jid), 'salt_master': str(master_id)})

    async def process(
        self,
        match: re.Match,
        master_id: str,
        data: MessageDataType,
        job: JobModel | None = None,
        tid: str | None = None,
    ) -> None:
        if not job:
            return

        jid: str = match.group('jid')
        mid: str = match.group('mid')
        function = data['fun']
        return_data = data.pop('return')

        if tid:
            logger.info('Job %s (task %s) return for %s, function %s', jid, tid, mid, function)
        else:
            logger.info('Job %s return for %s, function %s', jid, mid, function)

        job_return = await self._save_job_return(
            master_id=master_id, jid=jid, mid=mid, job=job, data=data, return_data=return_data
        )
        await self.job_service.update_status(jid=JID(jid))

        if tid:
            await process_task_job_return.kiq(jid=jid, minion_id=mid)  # type: ignore

        await self._process_return(job_return=job_return)
        await self._send_presence(master_id=master_id, mid=mid, data=data)

        raise StopProcessing()

    @classmethod
    def _inventory_state_predicate(cls, job_return: JobReturnModel) -> bool:
        if job_return.fun not in ('state.apply', 'state.sls'):
            return False

        fun_args = job_return.fun_args or []
        if cls.INVENTORY_STATE in fun_args:
            return True

        def check_kwargs(ret_kwargs: dict[str, Any]) -> bool:
            mods = ret_kwargs.get('mods')
            if mods == cls.INVENTORY_STATE or (isinstance(mods, list) and cls.INVENTORY_STATE in mods):
                return True

            return False

        # Check inventory in kwargs
        for arg in fun_args:
            if isinstance(arg, dict) and check_kwargs(arg):
                return True

        return check_kwargs(job_return.fun_kwarg or {})

    async def _process_return(self, job_return: JobReturnModel) -> None:
        if job_return.fun == 'grains.items':
            await self._process_grains(job_return=job_return)
        elif job_return.fun == 'inventory.get':
            logger.debug('Got inventory.get return for %s', job_return.minion_id)
            await self._notify_on_inventory_fun(job_return=job_return)
        elif self._inventory_state_predicate(job_return=job_return):
            logger.debug('Got inventory state return for %s', job_return.minion_id)
            await self._notify_on_inventory_state(job_return=job_return)

    async def _save_job_return(
        self, master_id: str, jid: str, mid: str, job: JobModel, data: dict, return_data: Any
    ) -> JobReturnModel:
        hash_name = f'master:{master_id}:job:{jid}:return-data'
        async with self.redis_client.pipeline() as pipe:
            pipe = pipe.hset(name=hash_name, key=mid, value=json.dumps(return_data))
            if SETTINGS.jobs_return_data_expire_ttl is not None:
                pipe = pipe.expire(name=hash_name, time=SETTINGS.jobs_return_data_expire_ttl)
            await pipe.execute()

        is_new_return = False

        try:
            payload = {
                **data,
                'source': job.source,
                'user': job.user,
                'stamp_job': job.stamp,
            }
            job_return = await self.job_return_service.create(
                data=JobReturnCreateSchema.model_validate(payload),
                notify=True,
            )
            is_new_return = True
        except DuplicateKeyException:
            try:
                job_return = await self.job_return_service.update(
                    query={'jid': jid, 'salt_master': master_id, 'minion_id': mid, 'retcode': None},
                    data=JobReturnUpdateSchema.model_validate(
                        {'source': job.source, 'user': job.user, 'stamp_job': job.stamp, **data}
                    ),
                    notify=True,
                )
                is_new_return = True
            except NotFoundException:
                job_return = await self.job_return_service.get(
                    query={'jid': jid, 'salt_master': master_id, 'minion_id': mid}
                )

        # TODO (@): Temporary! Remove this after frontend changes to use WS with job-returns
        await self.job_service.update(query=job.id, data={}, notify=True)

        if is_new_return and job.source and job.source.type == 'migration':
            await self.broker.connect()
            job_return.data = return_data
            await self.broker.publish(job_return, 'migration_job_return')

        return job_return

    @staticmethod
    async def _send_inventory_data(job_return: JobReturnModel, path: list[str | int]) -> None:
        if not SETTINGS.is_module_inventory_on:
            return

        message_to_inventory = InventoryPutEventBusMessage(sender='core', target='inventory', path=path)

        message_to_inventory.minions.append(
            InventoryPutForMinion(
                minion_id=job_return.minion_id,
                master_id=job_return.salt_master,
                job_return={'return': job_return.data},
            )
        )

        await send_message(message=message_to_inventory, queue='inventory_put_data')

    async def _notify_on_inventory_fun(self, job_return: JobReturnModel) -> None:
        if job_return.retcode != 0:
            logger.warning('inventory.get failed for JID=%s, minion=%s', job_return.jid, job_return.minion_id)
            return

        await self._send_inventory_data(job_return=job_return, path=['return'])

    async def _notify_on_inventory_state(self, job_return: JobReturnModel) -> None:
        if job_return.retcode != 0:
            logger.warning(
                '"state.apply inventory" get failed for JID=%s, minion=%s', job_return.jid, job_return.minion_id
            )
            return

        if not job_return.data:
            return

        mod_name = None
        for mod, mod_data in job_return.data.items():
            if mod_data['name'] == 'inventory.get':
                if mod_data['result'] is not True:
                    logger.warning(
                        'Calling inventory.get from state seems failed for JID=%s, minion=%s',
                        job_return.jid,
                        job_return.minion_id,
                    )
                    return
                mod_name = mod
                break
        else:
            logger.error(
                'Failed to find inventory.get data for JID=%s, minion=%s',
                job_return.jid,
                job_return.minion_id,
            )
            return

        await self._send_inventory_data(job_return=job_return, path=['return', mod_name, 'changes', 'ret'])

    async def _process_grains(self, job_return: JobReturnModel) -> None:
        logger.debug('Processing grains for %s', job_return.minion_id)
        if not job_return.data:
            return

        await self.minion_service.process_grains(
            master_id=job_return.salt_master, minion_id=job_return.minion_id, grains=job_return.data
        )

    async def _send_presence(self, master_id: str, mid: str, data: dict[str, Any]) -> None:
        await self.minion_service.process_presence(master_id=master_id, minions=[mid], stamp=data['stamp'].timestamp())

    async def _extract_job_status(self, data: MessageDataType) -> str:
        if data.get(self._STATUS_SUCCESS, False):
            return self._STATUS_SUCCESS
        elif isinstance(data['return'], dict):
            stage_results = []
            for stage in data['return'].values():
                stage_results.append(stage.get('result', False))
            if all(r is False for r in stage_results):
                return self._STATUS_FAILED
            elif any(r is True for r in stage_results):
                return self._STATUS_PARTIAL_SUCCESS
        return self._STATUS_FAILED

    async def _prepare_metrics_data(
        self, match: re.Match, master_id: str, tag: str, data: MessageDataType, tid: str | None = None
    ) -> dict:
        metrics_data = await super()._prepare_metrics_data(match=match, master_id=master_id, tag=tag, data=data)
        metrics_data.update(
            {
                'jid': match.group('jid'),
                'minion_id': match.group('mid'),
                'stamp': format_iso8601_z(data['stamp']),
            }
        )

        if tid:
            metrics_data.update({'tid': tid, 'job_status': await self._extract_job_status(data)})

        return metrics_data
