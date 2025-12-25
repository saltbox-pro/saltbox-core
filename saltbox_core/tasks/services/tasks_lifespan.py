from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobStatus
from saltbox_core.jobs.services.job_return_service import JobReturnService, get_job_return_service
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.minion_collections.schemas.minion_schemas import MinionSimpleSchema
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.tasks.exceptions import TaskServiceException
from saltbox_core.tasks.schemas.task import TaskModel, TaskType
from saltbox_core.tasks.schemas.tasks_minion import TaskMinionJobStatus, TaskMinionStatus
from saltbox_core.tasks.schemas.tasks_status import TaskStatus
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_core.tasks.services.tasks_minion import TaskMinionService, get_task_minion_service
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
        task: TaskModel | None = None,
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

    async def get_task(self) -> TaskModel:
        if self.__task:
            return self.__task
        elif self.task_id:
            self.__task = await self.task_service.get(query=self.task_id)
            return self.__task

        msg = 'Task does not set'
        raise TaskServiceException(msg)

    async def update_task(self, notify: bool = True, **kwargs: Any) -> TaskModel:
        task = await self.get_task()

        self.__task = await self.task_service.update(query=task.id, data={**kwargs}, notify=notify)

        return self.__task

    async def run(self, force: bool = False) -> None:
        task = await self.get_task()

        if (task.status and task.status.type in [TaskStatus.created, TaskStatus.stopped]) or force:
            await self.update_task(status=TaskStatus.running)

    async def __stop_jobs(self) -> None:
        task = await self.get_task()

        task_jobs = await self.job_service.get_list(
            query={'source.type': 'task', 'source.id': str(task.id), 'status': {'$ne': JobStatus.finished}},
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
            for minion_id in minions_ids:
                await self.task_minion_service.update(query=minion_id, data={'status': TaskMinionStatus.pending})

            await self.update_task(status=TaskStatus.running)

    async def _batch_size(self, salt_master: str) -> int:
        # TODO: Need algorithm to get batch size

        task = await self.get_task()

        if task.batch_size:
            return task.batch_size

        return 100

    async def sync_jobs(self) -> None:
        task = await self.get_task()

        # TODO: Sync task jobs
        logger.debug('Syncing jobs for task %s', task.id)

    async def check_unactive_minions(self, master: str, batch_size: int) -> None:
        task = await self.get_task()

        minions = await self.task_minion_service.get_list(
            query={
                'task_id': task.id,
                'master': master,
                'status': TaskMinionStatus.pending,
            },
            limit=batch_size * 3,
            skip=0,
            projection_model=MinionSimpleSchema,
        )

        if minions:
            await self.job_service.create(
                data=JobCreateSchema.model_validate(
                    {
                        'tgt': [minion.minion_id for minion in minions],
                        'tgt_type': 'list',
                        'salt_master': master,
                        'fun': 'test.ping',
                        'source': Source(type='task_system', id=str(task.id)),
                    },
                ),
                projection_model=EmptyModel,
            )

    @staticmethod
    def __active_dt() -> datetime:
        # TODO: Get from settings
        return utc_now() - timedelta(seconds=60 * 10)

    @staticmethod
    def __timedelta_to_sync_task() -> timedelta:
        # TODO: Get from settings
        return timedelta(seconds=60 * 10)

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
        )

        if minions:
            job = await self.job_service.create(
                data=JobCreateSchema.model_validate(
                    {
                        'tgt': [minion.minion_id for minion in minions],
                        'tgt_type': 'list',
                        'salt_master': master,
                        'fun': task.fun,
                        'arg': task.arg,
                        'kwarg': task.kwarg,
                        'source': Source(type='task', id=str(task.id)),
                    }
                )
            )

            for minion in minions:
                await self.task_minion_service.update(
                    query=minion.id,
                    data={
                        'status': TaskMinionStatus.in_work,
                        'start_last_dt': utc_now(),
                        'jobs': {**minion.jobs, job.jid: TaskMinionJobStatus.created},
                    },
                )

        return len(minions)

    async def handle_running_status(self) -> None:
        task = await self.get_task()

        if task.status and task.status.type != TaskStatus.running:
            return

        if task.task_type == TaskType.policy:
            await self.task_service.fill_task_minions(task=task)

        total_count_minions_in_new_job = 0
        total_count_active_jobs = 0

        for master in await self.master_service.get_accepted_list():
            active_jobs_count = await self.job_service.count(
                query={
                    'source.type': 'task',
                    'source.id': str(task.id),
                    'salt_master': master.master_id,
                    'status': {'$in': [JobStatus.in_queue, JobStatus.started, JobStatus.waiting_returns]},
                }
            )

            batch_size = await self._batch_size(master.master_id)
            while active_jobs_count < task.max_jobs_count_at_same_time:
                minions_in_job_count = await self.create_job(master.master_id, batch_size)
                total_count_minions_in_new_job += minions_in_job_count

                if minions_in_job_count < batch_size:
                    await self.check_unactive_minions(master=master.master_id, batch_size=batch_size)
                    break

                active_jobs_count += 1

            total_count_active_jobs += active_jobs_count

        if (
            total_count_active_jobs == 0
            and total_count_minions_in_new_job == 0
            and not await self.task_minion_service.exists(
                query={
                    'task_id': task.id,
                    'status': {'$in': [TaskMinionStatus.pending, TaskMinionStatus.busy, TaskMinionStatus.in_work]},
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
            query={'source.type': 'task', 'source.id': str(task.id), 'status': {'$ne': JobStatus.finished}}
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
            if await self.task_service.fill_task_minions(task=task):
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
