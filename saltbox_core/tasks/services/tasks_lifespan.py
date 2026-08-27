from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_return_schemas import JobReturnStatus, JobReturnTgtOnlySchema
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobJidOnlySchema, JobStatus
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.tasks.exceptions import TaskServiceException
from saltbox_core.tasks.policy_ordering import PolicyExecutionInfo, is_active_predecessor, resolve_execution_status
from saltbox_core.tasks.schemas.task import TaskForLifespanModel, TaskModel, TaskType
from saltbox_core.tasks.schemas.tasks_minion import (
    TaskMinionForRequirementsCheckSchema,
    TaskMinionStatus,
    TaskMinionTgtOnlySchema,
)
from saltbox_core.tasks.schemas.tasks_status import TaskStatus
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
from saltbox_core.utilities.jid import JID
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.db.schemas_base import Source
from saltbox_sdk.utilities.helpers import utc_now


class TaskLifespanService:
    def __init__(
        self,
        rdb: Redis,
        task_service: TaskService,
        task_minion_service: TaskMinionService,
        master_service: MasterService,
        job_service: JobService,
        job_return_service: JobReturnService,
        minion_service: MinionService,
        collection_service: CollectionService,
        task_id: PyObjectId | None = None,
        task: TaskForLifespanModel | None = None,
    ):
        self.rdb = rdb
        self.task_service = task_service
        self.task_minion_service = task_minion_service
        self.master_service = master_service
        self.job_service = job_service
        self.job_return_service = job_return_service
        self.minion_service = minion_service
        self.collection_service = collection_service
        self._mongo_db = get_mongo_db()

        if task_id and task:
            msg = "TaskLifespanService can't accept both `task_id` and `task` args at the same time"
            raise TaskServiceException(msg)

        if task_id is None and task is None:
            msg = "TaskLifespanService can't accept arguments `task_id` and `task` equal to None at the same time"
            raise TaskServiceException(msg)

        self.task_id = task_id
        self.__task = task

    async def get_task(self) -> TaskForLifespanModel:
        if self.__task:
            return self.__task
        elif self.task_id:
            self.__task = await self.task_service.get(query=self.task_id, projection_model=TaskForLifespanModel)
            return self.__task

        msg = 'Task does not set'
        raise TaskServiceException(msg)

    async def get_full_task(self) -> TaskModel:
        task = await self.get_task()

        return await self.task_service.get(query=task.id)

    async def update_task(self, notify: bool = True, **kwargs: Any) -> TaskForLifespanModel:
        task = await self.get_task()

        await self.task_service.update(query=task.id, data={**kwargs}, notify=notify)
        self.__task = await self.task_service.get(query=task.id, projection_model=TaskForLifespanModel)

        return self.__task

    async def run(self, force: bool = False) -> None:
        task = await self.get_task()

        if (task.status and task.status.type in [TaskStatus.created, TaskStatus.stopped]) or force:
            await self.update_task(status=TaskStatus.running)

    async def __stop_jobs(self) -> None:
        task = await self.get_task()

        task_jobs = await self.job_service.get_list(
            query={
                'source.type': 'task',
                'source.id': str(task.id),
                'status': {'$nin': [JobStatus.finished, JobStatus.launch_error]},
            },
            limit=0,
            skip=0,
            projection_model=EmptyModel,
        )

        for task_job in task_jobs:
            await self.job_service.stop_job(task_job.id)

    async def stop(self) -> None:
        task = await self.get_task()

        if task.status and task.status.type in [TaskStatus.running, TaskStatus.wait_minions]:
            await self.__stop_jobs()
            await self.update_task(status=TaskStatus.stopping)

    async def restart_on_minions(self, minions_ids: list[PyObjectId]) -> None:
        task = await self.get_task()

        if task.status and task.status.type != TaskStatus.stopping:
            await self.task_minion_service.bulk_update(
                query={'_id': {'$in': minions_ids}},
                data={'status': TaskMinionStatus.pending, 'check_unactive_last_job_dt': None},
            )

            await self.update_task(status=TaskStatus.running)

    async def _batch_size(self, salt_master: str) -> int:
        # TODO: Need algorithm to get batch size

        task = await self.get_task()

        return task.batch_size

    async def sync_jobs(self) -> None:
        task = await self.get_task()

        logger.debug('Syncing jobs for task %s', task.id)

        task_jobs = await self.job_service.get_list(
            query={
                'source.type': 'task',
                'source.id': str(task.id),
                'status': JobStatus.running,
            },
            limit=0,
            skip=0,
            projection_model=JobJidOnlySchema,
        )

        for task_job in task_jobs:
            await self.job_service.update_status(jid=JID(task_job.jid), notify=True)

    async def check_unactive_minions(self, master: str, batch_size: int) -> None:
        task = await self.get_task()

        minions = await self.task_minion_service.get_list(
            query={
                'task_id': task.id,
                'master': master,
                'status': TaskMinionStatus.pending,
                'last_activity': {'$lt': self.__active_dt()},
                '$and': [
                    {
                        '$or': [
                            {'last_check_unactive_dt': None},
                            {'last_check_unactive_dt': {'$lt': utc_now() - self.__timedelta_to_sync_task() * 2}},
                        ],
                    },
                    {
                        '$or': [
                            {'check_unactive_last_job_dt': None},
                            {'check_unactive_last_job_dt': {'$lt': utc_now() - self.__timedelta_to_sync_task()}},
                        ]
                    },
                ],
            },
            limit=batch_size * 3,
            skip=0,
            projection_model=TaskMinionTgtOnlySchema,
        )

        if minions:
            await self.task_minion_service.bulk_update(
                query={'_id': {'$in': [minion.id for minion in minions]}},
                data={'check_unactive_last_job_dt': utc_now()},
            )

            await self.job_service.create(
                data=JobCreateSchema.model_validate(
                    {
                        'tgt': [minion.minion_id for minion in minions],
                        'tgt_type': 'list',
                        'salt_master': master,
                        'fun': 'test.ping',
                        'source': Source(type='task_system', id=str(task.id)),
                        'user': task.user,
                    },
                ),
            )

    @staticmethod
    def __active_dt() -> datetime:
        # TODO: Get from settings
        return utc_now() - timedelta(seconds=60 * 10)

    @staticmethod
    def __timedelta_to_sync_task() -> timedelta:
        # TODO: Get from settings
        return timedelta(seconds=60 * 10)

    async def get_busy_minions_by_tgt(self, tgt: dict[str, list[str]]) -> list[dict[str, str]]:
        task = await self.get_task()
        busy_minions_tgt: list[dict[str, str]] = []

        for master, minions_ids in tgt.items():
            if task.fun == 'state.apply':
                for busy_minion in await self.job_return_service.get_list(
                    query={
                        'fun': 'state.apply',
                        'status': JobReturnStatus.waiting,
                        'salt_master': master,
                        'minion_id': {'$in': minions_ids},
                    },
                    projection_model=JobReturnTgtOnlySchema,
                ):
                    busy_minions_tgt.append({'minion_id': busy_minion.minion_id, 'master': busy_minion.salt_master})

            for busy_task_minion in await self.task_minion_service.get_list(
                query={
                    'task_id': {'$ne': task.id},
                    'status': TaskMinionStatus.in_work,
                    'master': master,
                    'minion_id': {'$in': minions_ids},
                },
                projection_model=TaskMinionTgtOnlySchema,
            ):
                busy_minion_tgt = {'minion_id': busy_task_minion.minion_id, 'master': busy_task_minion.master}
                if busy_minion_tgt not in busy_minions_tgt:
                    busy_minions_tgt.append(busy_minion_tgt)

        return busy_minions_tgt

    async def check_busy_task_minions(self) -> None:
        task = await self.get_task()

        pending_minions = await self.task_minion_service.get_list(
            query={'task_id': task.id, 'status': TaskMinionStatus.pending}, projection_model=TaskMinionTgtOnlySchema
        )

        if pending_minions:
            pending_minions_ids_by_master: dict[str, list[str]] = {}

            for pending_minion in pending_minions:
                pending_minions_ids_by_master.setdefault(pending_minion.master, []).append(pending_minion.minion_id)

            busy_minions_tgt = await self.get_busy_minions_by_tgt(tgt=pending_minions_ids_by_master)

            if busy_minions_tgt:
                await self.task_minion_service.bulk_update(
                    query={
                        'task_id': task.id,
                        'status': TaskMinionStatus.pending,
                        '$or': busy_minions_tgt,
                    },
                    data={'status': TaskMinionStatus.busy},
                )

        busy_minions = await self.task_minion_service.get_list(
            query={'task_id': task.id, 'status': TaskMinionStatus.busy}, projection_model=TaskMinionTgtOnlySchema
        )

        if busy_minions:
            busy_minions_ids_by_master: dict[str, list[str]] = {}

            for busy_minion in busy_minions:
                busy_minions_ids_by_master.setdefault(busy_minion.master, []).append(busy_minion.minion_id)

            busy_minions_tgt = await self.get_busy_minions_by_tgt(tgt=busy_minions_ids_by_master)
            non_busy_minions_tgt: list[dict[str, str]] = []

            for busy_minion in busy_minions:
                busy_minion_tgt = {'minion_id': busy_minion.minion_id, 'master': busy_minion.master}
                if busy_minion_tgt not in busy_minions_tgt:
                    non_busy_minions_tgt.append(busy_minion_tgt)

            if non_busy_minions_tgt:
                await self.task_minion_service.bulk_update(
                    query={
                        'task_id': task.id,
                        'status': TaskMinionStatus.busy,
                        '$or': non_busy_minions_tgt,
                    },
                    data={'status': TaskMinionStatus.pending},
                )

    async def check_policy_requirements_task_minions(self) -> None:
        task = await self.get_task()

        if task.task_type != TaskType.policy:
            return

        candidates = await self.task_minion_service.get_list(
            query={
                'task_id': task.id,
                'status': {'$in': [TaskMinionStatus.pending, TaskMinionStatus.blocked, TaskMinionStatus.unreachable]},
            },
            projection_model=TaskMinionForRequirementsCheckSchema,
        )

        if not candidates:
            return

        collections_by_id = await self.task_minion_service.get_collections_order_map()
        ids_by_new_status: dict[TaskMinionStatus, list[PyObjectId]] = defaultdict(list)
        task_status_cache: dict[PyObjectId, TaskStatus] = {}

        for candidate in candidates:
            policies = await self.task_minion_service.get_policies_for_minion(
                minion_inner_id=candidate.minion_inner_id, collections_by_id=collections_by_id
            )

            missing_task_ids = [policy.task_id for policy in policies if policy.task_id not in task_status_cache]
            if missing_task_ids:
                task_status_cache.update(await self.task_service.get_task_statuses(task_ids=missing_task_ids))

            execution_info = [
                PolicyExecutionInfo(task_id=policy.task_id, status=policy.status, requirements=policy.task.requirements)
                for policy in policies
                if policy.task_id == task.id
                or is_active_predecessor(task_status_cache.get(policy.task_id), policy.status)
            ]

            new_status = resolve_execution_status(task_id=task.id, ordered_policies=execution_info)

            if new_status is None:
                logger.warning(f'Policy task {task.id} not found in its own minion policies list')
                continue

            if new_status != candidate.status:
                ids_by_new_status[new_status].append(candidate.id)

        for new_status, ids in ids_by_new_status.items():
            await self.task_minion_service.bulk_update(query={'_id': {'$in': ids}}, data={'status': new_status})

    async def create_job(self, master: str, batch_size: int) -> int:
        task = await self.get_task()

        minions = await self.task_minion_service.get_list(
            query={
                'task_id': task.id,
                'master': master,
                'status': TaskMinionStatus.pending,
                '$or': [
                    {'start_last_dt': None},
                    {'start_last_dt': {'$lte': utc_now() - timedelta(seconds=task.retry_delay)}},
                ],
                'last_activity': {'$gte': self.__active_dt()},
            },
            skip=0,
            limit=batch_size,
            projection_model=TaskMinionTgtOnlySchema,
        )

        if minions:
            ttl: int | None = task.ttl

            if ttl is None and task.task_template and task.task_template.defaults:
                ttl = task.task_template.defaults.ttl

            await self.job_service.create(
                data=JobCreateSchema.model_validate(
                    {
                        'tgt': [minion.minion_id for minion in minions],
                        'tgt_type': 'list',
                        'salt_master': master,
                        'fun': task.fun,
                        'arg': task.arg,
                        'kwarg': task.kwarg,
                        'ttl': ttl,
                        'source': Source(type='task', id=str(task.id)),
                        'user': task.user,
                    }
                ),
                extra_pillarenv=[f'task:{task.id!s}'],
            )

            await self.task_minion_service.bulk_update(
                query={'_id': {'$in': [minion.id for minion in minions]}},
                data={
                    'status': TaskMinionStatus.in_work,
                    'start_last_dt': utc_now(),
                },
            )

        return len(minions)

    async def handle_running_status(self) -> None:
        task = await self.get_task()

        if task.status and task.status.type != TaskStatus.running:
            return

        if task.task_type == TaskType.policy:
            await self.task_service.fill_task_minions(
                task_id=task.id, target_collection_id=task.target_collection_id, target_query=task.target_query
            )

        await self.check_policy_requirements_task_minions()
        await self.check_busy_task_minions()

        total_count_minions_in_new_job = 0
        total_count_active_jobs = 0

        for master in await self.master_service.get_accepted_list():
            active_jobs_count = await self.job_service.count(
                query={
                    'source.type': 'task',
                    'source.id': str(task.id),
                    'salt_master': master.master_id,
                    'status': {'$in': [JobStatus.starting, JobStatus.running]},
                }
            )

            batch_size = await self._batch_size(master.master_id)
            while active_jobs_count < task.max_jobs_count_at_same_time:
                minions_in_job_count = await self.create_job(master.master_id, batch_size)
                total_count_minions_in_new_job += minions_in_job_count

                if minions_in_job_count > 0:
                    active_jobs_count += 1

                if minions_in_job_count < batch_size or (batch_size == 0 and minions_in_job_count == 0):
                    await self.check_unactive_minions(master=master.master_id, batch_size=batch_size)
                    break

            total_count_active_jobs += active_jobs_count

        if (
            total_count_active_jobs == 0
            and total_count_minions_in_new_job == 0
            and not await self.task_minion_service.exists(
                query={
                    'task_id': task.id,
                    'status': {
                        '$in': [
                            TaskMinionStatus.pending,
                            TaskMinionStatus.busy,
                            TaskMinionStatus.in_work,
                            TaskMinionStatus.blocked,
                        ]
                    },
                }
            )
        ):
            await self.update_task(
                status=TaskStatus.wait_minions if task.task_type == TaskType.policy else TaskStatus.finished
            )
        else:
            if utc_now() - task.modified > self.__timedelta_to_sync_task():
                await self.sync_jobs()

    async def handle_stopping_status(self) -> None:
        task = await self.get_task()

        if task.status and task.status.type != TaskStatus.stopping:
            return

        if await self.job_service.exists(
            query={
                'source.type': 'task',
                'source.id': str(task.id),
                'status': {'$nin': [JobStatus.finished, JobStatus.launch_error]},
            }
        ):
            # Sync jobs when task has no updates a long time
            if utc_now() - task.modified > self.__timedelta_to_sync_task():
                await self.sync_jobs()

            return

        await self.update_task(status=TaskStatus.stopped)

    async def handle_wait_minion_status(self) -> None:
        task = await self.get_task()

        if task.status and task.status.type != TaskStatus.wait_minions:
            return

        if task.task_type == TaskType.policy:
            if await self.task_service.fill_task_minions(
                task_id=task.id, target_collection_id=task.target_collection_id, target_query=task.target_query
            ):
                await self.update_task(status=TaskStatus.running)
            else:
                await self.check_policy_requirements_task_minions()

                if await self.task_minion_service.exists(
                    query={'task_id': task.id, 'status': TaskMinionStatus.pending}
                ):
                    await self.update_task(status=TaskStatus.running)
        else:
            await self.update_task(status=TaskStatus.running)

    async def process(self) -> None:
        task = await self.get_task()

        if not task.status:
            return

        if task.status and task.status.type not in [TaskStatus.running, TaskStatus.stopping, TaskStatus.wait_minions]:
            return

        handler = {
            TaskStatus.wait_minions: self.handle_wait_minion_status,
            TaskStatus.running: self.handle_running_status,
            TaskStatus.stopping: self.handle_stopping_status,
        }.get(task.status.type)

        if not handler:
            logger.warning(f'Processing task ({task.id}) with wring status {task.status}')
            return

        await handler()


def get_task_lifespan_service(
    rdb: Annotated[Redis, Depends(get_redis)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    task_minion_service: Annotated[TaskMinionService, Depends(get_task_minion_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
    job_service: Annotated[JobService, Depends(get_job_service)],
    job_return_service: Annotated[JobReturnService, Depends(get_job_return_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    tid: PyObjectId | None = None,
) -> TaskLifespanService:
    return TaskLifespanService(
        rdb=rdb,
        task_service=task_service,
        task_minion_service=task_minion_service,
        master_service=master_service,
        job_service=job_service,
        job_return_service=job_return_service,
        minion_service=minion_service,
        collection_service=collection_service,
        task_id=tid,
    )
