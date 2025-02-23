import logging.config
from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.db.redis import RedisDependency
from salt_box_core.jobs.exceptions import JobCreateException
from salt_box_core.jobs.schemas import JobCreate, JobResult
from salt_box_core.jobs.services import JobService, get_job_service
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionModel
from salt_box_core.minion_collections.schemas.minion_schemas import MinionModel
from salt_box_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service
from salt_box_core.tasks.schemas.task_schemas import (
    TaskForceUpdateSchema,
    TaskJob,
    TaskJobReturnStatus,
    TaskJobStatus,
    TaskJobTarget,
    TaskJobTargetType,
    TaskModel,
    TaskStatus,
)
from salt_box_core.tasks.services.tasks import TaskService, get_task_service
from salt_box_core.utilities.exceptions import ServiceError
from salt_box_core.utilities.helpers import get_now_stamp_str
from salt_box_core.utilities.jid import JID
from salt_box_core.utilities.mongo_query_to_salt_tgt_converter import MongoQueryToSaltTgtConverter

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class TaskLifespanService:
    def __init__(
        self,
        rdb: Redis,
        task_service: TaskService,
        job_service: JobService,
        minion_service: MinionService,
        collection_service: CollectionService,
        task_id: PyObjectId | None = None,
        task: TaskModel | None = None,
    ):
        self.rdb = rdb
        self.task_service = task_service
        self.job_service = job_service
        self.minion_service = minion_service
        self.collection_service = collection_service
        self._mongo_db = get_mongo_db()

        if task_id and task:
            msg = "TaskLifespanService can't accept both `task_id` and `task` args at the same time"
            raise ServiceError(msg)

        if task_id is None and task is None:
            msg = "TaskLifespanService can't accept arguments `task_id` and `task` equal to None at the same time"
            raise ServiceError(msg)

        self.task_id = task_id
        self.__task = task

    async def get_task(self) -> TaskModel:
        if self.__task:
            return self.__task
        elif self.task_id:
            self.__task = await self.task_service.get(query=self.task_id)
            return self.__task

        msg = 'Task does not set'
        raise ServiceError(msg)

    async def update_task(self, notify: bool = True, **kwargs: Any) -> TaskModel:
        task: TaskModel = await self.get_task()

        for attr, value in kwargs.items():
            task.__setattr__(attr, value)

        self.__task = await self.task_service.update(
            query=task.id, data=TaskForceUpdateSchema.model_validate(task.model_dump()), notify=notify
        )

        return self.__task

    async def run(self) -> None:
        task = await self.get_task()

        if task.status in [TaskStatus.created, TaskStatus.stopped]:
            await self.update_task(status=TaskStatus.running)

    async def __stop_jobs(self) -> None: ...  # TODO (i.moshkov): stop jobs

    async def stop(self) -> None:
        task: TaskModel = await self.get_task()

        if task.status == TaskStatus.running:
            await self.__stop_jobs()
            await self.update_task(status=TaskStatus.stopped)

    async def __can_start_job(self) -> bool:
        task: TaskModel = await self.get_task()

        for job in task.jobs:
            if job.status == TaskJobStatus.running:
                return False

        return True

    async def __build_targets_list_from_dict(self, targets: dict[str, list[str]]) -> list[TaskJobTarget]:
        task: TaskModel = await self.get_task()
        result: list[TaskJobTarget] = []

        targets_lists: dict[str, list[list[str]]] = {}
        temp_targets_lists: dict[str, list[str]] = {}

        for master, minions_ids in targets.items():
            for minion_id in minions_ids:
                temp_targets_lists.setdefault(master, []).append(minion_id)

                if task.batch_size and len(temp_targets_lists[master]) >= task.batch_size:
                    targets_lists.setdefault(master, []).append(temp_targets_lists[master][:])
                    temp_targets_lists[master] = []
        else:
            for master, temp_targets_list in temp_targets_lists.items():
                if len(temp_targets_list):
                    targets_lists.setdefault(master, []).append(temp_targets_list)

        for master, targets_list in targets_lists.items():
            for tgt_list in targets_list:
                result.append(TaskJobTarget(tgt=','.join(tgt_list), type=TaskJobTargetType.list, master=master))

        return result

    async def __get_task_targeting(self) -> list[TaskJobTarget]:
        task: TaskModel = await self.get_task()
        collection: CollectionModel = await self.collection_service.get(task.collection_id)
        query: dict = collection.query

        if task.query and task.minions:
            query = {
                '$and': [query, task.query, {'_id': {'$in': [PyObjectId(minion_id) for minion_id in task.minions]}}]
            }
        elif task.query:
            query = {'$and': [query, task.query]}
        elif task.minions:
            query = {'$and': [query, {'_id': {'$in': [PyObjectId(minion_id) for minion_id in task.minions]}}]}

        if task.minions or task.batch_size:
            minions: list[MinionModel] = await self.minion_service.get_list(query=query, limit=0, skip=0)

            _result: dict[str, list[str]] = {}

            for minion in minions:
                _result.setdefault(minion.master, []).append(minion.minion_id)

            return await self.__build_targets_list_from_dict(_result)

        return [
            TaskJobTarget(
                tgt=MongoQueryToSaltTgtConverter.convert_from_dict(query),
                master='salt-master',  # TODO (i.moshkov): getting salt master
                type=TaskJobTargetType.compound,
            )
        ]

    async def __add_to_targets_queue(self, targets: list[TaskJobTarget]) -> None:
        task: TaskModel = await self.get_task()

        if task.targets_queue is None:
            task.targets_queue = []

        for target in targets:
            task.targets_queue.append(target)

    async def __init_fill_jobs_queue(self) -> None:
        targets: list[TaskJobTarget] = await self.__get_task_targeting()
        await self.__add_to_targets_queue(targets)

    async def __check_job_returns(self, job: TaskJob) -> None:
        task: TaskModel = await self.get_task()
        job_returns: list[JobResult] = await self.job_service.get_job_all_returns(JID(job.jid))
        targets_with_failed_job: dict[str, list[str]] = {}

        for return_data in job_returns:
            minion_id: str = return_data.id
            returns_status = job.returns_statuses.get(minion_id, TaskJobReturnStatus.waiting)

            if returns_status != TaskJobReturnStatus.waiting:
                continue

            if return_data.success is True:
                job.returns_statuses[minion_id] = TaskJobReturnStatus.succeeded
            else:
                task.minions_retries_counts.setdefault(minion_id, 0)
                task.minions_retries_counts[minion_id] += 1

                if task.minions_retries_counts[minion_id] <= task.max_retries - 1:
                    targets_with_failed_job.setdefault(job.target.master, []).append(minion_id)
                else:
                    task.failed_for_minions.append(minion_id)

                job.returns_statuses[minion_id] = TaskJobReturnStatus.failed

            job.finished_stamp = get_now_stamp_str()

        targets = await self.__build_targets_list_from_dict(targets_with_failed_job)
        await self.__add_to_targets_queue(targets)

    async def __check_running_jobs(self) -> None:
        task: TaskModel = await self.get_task()

        for job in task.jobs:
            if job.status != TaskJobStatus.running:
                continue

            await self.__check_job_returns(job=job)

            if not len(job.returns_statuses.keys()):
                continue

            # TODO (i.moshkov): process long-time jobs
            if all(status == TaskJobReturnStatus.succeeded for status in job.returns_statuses.values()):
                job.status = TaskJobStatus.succeeded
            elif not any(status == TaskJobReturnStatus.waiting for status in job.returns_statuses.values()):
                job.status = TaskJobStatus.failed

    async def __create_job(self, job_target: TaskJobTarget) -> None:
        task: TaskModel = await self.get_task()

        jid: JID = await self.job_service.create_job(
            JobCreate.model_validate(
                {
                    'jid_postfix': f't{task.id}',
                    'tgt': job_target.tgt,
                    'tgt_type': job_target.type,
                    'fun': task.fun,
                    'data': {
                        'args': task.task_args,
                        'kwargs': task.task_kwargs,
                    },
                    'salt_master': job_target.master,
                }
            )
        )

        task.jobs.append(
            TaskJob(
                jid=str(jid),
                target=job_target,
                # returns_statuses={minion_id: TaskJobReturnStatus.waiting for minion_id in job_target.tgt.split(',')},
                # TODO (i.moshkov): waiting status
            )
        )

    async def __rub_jobs(self) -> None:
        task: TaskModel = await self.get_task()

        if not task.targets_queue:
            return

        can_start_job: bool = await self.__can_start_job()

        if can_start_job:
            job_targeting = task.targets_queue.pop(0)

            try:
                await self.__create_job(job_target=job_targeting)
            except JobCreateException as error:
                logger.warning(error)
                task.targets_queue.append(job_targeting)

    async def process(self) -> None:
        task: TaskModel = await self.get_task()

        if task.status != TaskStatus.running:
            return
        if task.targets_queue is None:
            await self.__init_fill_jobs_queue()

        await self.__check_running_jobs()
        await self.__rub_jobs()

        if not task.targets_queue:
            for job in task.jobs:
                if job.status == TaskJobStatus.running:
                    break
            else:
                task.status = TaskStatus.finished

        await self.update_task(notify=True)


async def get_task_lifespan_service(
    rdb: RedisDependency,
    task_service: Annotated[TaskService, Depends(get_task_service)],
    job_service: Annotated[JobService, Depends(get_job_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    tid: PyObjectId | None = None,
) -> TaskLifespanService:
    return TaskLifespanService(
        rdb=rdb,
        task_service=task_service,
        job_service=job_service,
        minion_service=minion_service,
        collection_service=collection_service,
        task_id=tid,
    )
