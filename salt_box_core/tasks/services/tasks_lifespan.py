import logging.config
from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from salt_box_core.config import LOG_CONFIG
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.db.redis import RedisDependency
from salt_box_core.jobs.exceptions import JobCreateException, JobDoesNotExistsException
from salt_box_core.jobs.schemas import Job, JobCreate, JobResult
from salt_box_core.jobs.services import JobService, get_job_service
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionModel
from salt_box_core.minion_collections.schemas.minion_schemas import MinionModel
from salt_box_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service
from salt_box_core.tasks.schemas.task_schemas import (
    TaskJob,
    TaskJobReturnStatus,
    TaskJobStatus,
    TaskJobTarget,
    TaskJobTargetType,
    TaskMinion,
    TaskMinionJobStatus,
    TaskMinionStatus,
    TaskModel,
    TaskStatus,
    TaskUpdateSchema,
)
from salt_box_core.tasks.services.tasks import TaskService, get_task_service
from salt_box_core.utilities.exceptions import ServiceError
from salt_box_core.utilities.helpers import recursive_replace_dates, utc_now
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
            query=task.id,
            data=TaskUpdateSchema.model_validate(task.model_dump(exclude=set('id'))),
            notify=notify,
        )

        return self.__task

    async def run(self) -> None:
        task = await self.get_task()

        if task.status in [TaskStatus.created, TaskStatus.stopped]:
            await self.update_task(status=TaskStatus.running)

    async def __stop_jobs(self) -> None:
        task: TaskModel = await self.get_task()

        for jid in task.jobs.keys():
            await self.job_service.stop_job(JID(jid))

    async def stop(self) -> None:
        task: TaskModel = await self.get_task()

        if task.status == TaskStatus.running:
            await self.__stop_jobs()
            await self.update_task(status=TaskStatus.stopping)

    async def restart_failed(self) -> None:
        task: TaskModel = await self.get_task()

        if task.status == TaskStatus.finished:
            for minion in task.minions.values():
                if minion.status == TaskMinionStatus.failed:
                    minion.status = TaskMinionStatus.pending

            await self.__create_jobs(ignore_limits=True)
            await self.update_task(status=TaskStatus.running)

    async def restart_failed_on_minion(self, master: str, minion_id: str) -> None:
        task: TaskModel = await self.get_task()
        minion_key = self.__get_minion_key(master=master, minion_id=minion_id)

        if task.status != TaskStatus.finished:
            return

        try:
            minion = task.minions[minion_key]
        except IndexError:
            return

        if minion.status != TaskMinionStatus.failed:
            return

        minion.status = TaskMinionStatus.pending

        await self.__create_jobs(ignore_limits=True)
        await self.update_task(status=TaskStatus.running)

    async def __can_start_job(self, master: str | None = None) -> bool:
        task: TaskModel = await self.get_task()
        running_job_count: int = 0

        for job in task.jobs.values():
            if job.status == TaskJobStatus.running:
                if master and master != job.target.master:
                    continue

                running_job_count += 1

                if running_job_count >= task.max_jobs_count_at_same_time:
                    return False

        return True

    @staticmethod
    def __get_minion_key(master: str, minion_id: str) -> str:
        return f'{master}_{minion_id}'

    def __check_compound_compatible_query(self, _query: dict[str, Any]) -> bool:
        for query_key, query_item in _query.items():
            if query_key.startswith('grains.'):
                continue

            if query_key.startswith('$'):
                if isinstance(query_item, dict):
                    if self.__check_compound_compatible_query(query_item):
                        return True
                elif isinstance(query_item, list):
                    for item in [item for item in query_item if isinstance(item, dict)]:
                        if self.__check_compound_compatible_query(item):
                            return True
            else:
                return True

        return False

    async def __get__targeting_query(self) -> dict:
        task: TaskModel = await self.get_task()
        collection: CollectionModel = await self.collection_service.get(task.target_collection.id)
        query: dict = collection.query

        if task.target_query and task.target_minions:
            query = {
                '$and': [
                    query,
                    task.target_query,
                    {'_id': {'$in': [PyObjectId(minion_id) for minion_id in task.target_minions]}},
                ]
            }
        elif task.target_query:
            query = {'$and': [query, task.target_query]}
        elif task.target_minions:
            query = {'$and': [query, {'_id': {'$in': [PyObjectId(minion_id) for minion_id in task.target_minions]}}]}

        query = recursive_replace_dates(query)

        return query

    async def __fill_minions_by_targeting(self) -> None:
        task: TaskModel = await self.get_task()
        targeting_query = await self.__get__targeting_query()
        not_compound_compatible_query: bool = self.__check_compound_compatible_query(targeting_query)
        minions: list[MinionModel] = await self.minion_service.get_list(query=targeting_query, limit=0, skip=0)
        minions_by_master: dict[str, list[str]] = {}

        for minion in minions:
            if minion.master in task.target_masters or not len(task.target_masters):
                task.minions[self.__get_minion_key(minion.master, minion.minion_id)] = TaskMinion(
                    master=minion.master,
                    minion_id=minion.minion_id,
                )
                minions_by_master.setdefault(minion.master, []).append(minion.minion_id)

        if not_compound_compatible_query or task.batch_size:
            await self.__create_jobs()
        else:
            for master in task.target_masters:
                try:
                    await self.__create_job(
                        minions=minions_by_master[master],
                        compound=MongoQueryToSaltTgtConverter.convert_from_dict(query_dict=targeting_query),
                        master=master,
                    )
                except JobCreateException:
                    continue

    async def __create_job(self, master: str, minions: list[str], compound: str | None = None) -> None:
        task: TaskModel = await self.get_task()
        tgt: str = compound if compound else ','.join(minions)
        tgt_type: TaskJobTargetType = TaskJobTargetType.compound if compound else TaskJobTargetType.list

        jid: JID = await self.job_service.create_job(
            JobCreate.model_validate(
                {
                    'jid_postfix': f't{task.id}',
                    'tgt': tgt,
                    'tgt_type': tgt_type,
                    'fun': task.fun,
                    'data': {
                        'args': task.task_args,
                        'kwargs': task.task_kwargs,
                    },
                    'salt_master': master,
                }
            )
        )

        task.jobs[str(jid)] = TaskJob(
            jid=str(jid), target=TaskJobTarget(tgt=tgt, tgt_type=tgt_type, master=master), minions_by_targeting=minions
        )

        for minion_id in minions:
            minion = task.minions[self.__get_minion_key(master=master, minion_id=minion_id)]

            minion.status = TaskMinionStatus.in_work
            minion.jobs[str(jid)] = TaskMinionJobStatus.created
            minion.start_last_dt = task.jobs[str(jid)].created_dt

    async def __create_jobs(self, ignore_limits: bool = True) -> None:
        task: TaskModel = await self.get_task()
        minions_queue: dict[str, list[list[str]]] = {}

        for minion in task.minions.values():
            if minion.status == TaskMinionStatus.pending:
                if len(minion.jobs) >= task.max_retries and not ignore_limits:
                    minion.status = TaskMinionStatus.failed
                    continue

                minions_queue.setdefault(minion.master, [[]])

                if task.batch_size and 0 < task.batch_size <= len(minions_queue[minion.master][-1]):
                    minions_queue[minion.master].append([])

                minions_queue[minion.master][-1].append(minion.minion_id)

        for master, master_tgt_list in minions_queue.items():
            for tgt in master_tgt_list:
                if not await self.__can_start_job(master=master):
                    continue

                try:
                    await self.__create_job(minions=tgt, master=master)
                except JobCreateException:
                    continue

    async def __check_jobs(self) -> None:
        task: TaskModel = await self.get_task()

        for task_job in task.jobs.values():
            if task_job.status in [TaskJobStatus.failed, TaskJobStatus.succeeded]:
                continue

            try:
                job_data: Job = await self.job_service.get_job(JID(task_job.jid))

            except JobDoesNotExistsException:
                task_job.status = TaskJobStatus.failed
                continue

            if job_data.status == Job.JobStatus.in_queue:
                continue

            if not task_job.minions_from_salt:
                task_job.minions_from_salt = job_data.minions
                await self.__check_minions_in_job(task_job=task_job, job_data=job_data)

            await self.__check_job_returns(task_job=task_job, jid=JID(task_job.jid))
            await self.__update_task_job_status(task_job=task_job)

    async def __check_minions_in_job(self, task_job: TaskJob, job_data: Job) -> None:
        task: TaskModel = await self.get_task()

        for minion_id in task_job.minions_by_targeting:
            minion = task.minions[self.__get_minion_key(master=task_job.target.master, minion_id=minion_id)]

            if minion_id not in job_data.minions:
                minion.jobs[task_job.jid] = TaskMinionJobStatus.ignored

                if len(minion.jobs) >= task.max_retries:
                    minion.status = TaskMinionStatus.failed
                else:
                    minion.status = TaskMinionStatus.pending
            else:
                minion.jobs[task_job.jid] = TaskMinionJobStatus.in_work

        for minion_id in job_data.minions:
            task_job.returns_statuses.setdefault(minion_id, TaskJobReturnStatus.waiting)
            minion_key: str = self.__get_minion_key(master=task_job.target.master, minion_id=minion_id)

            if minion_key not in task.minions.keys():
                task.minions[minion_key] = TaskMinion(
                    minion_id=minion_id,
                    master=task_job.target.master,
                    jobs={task_job.jid: TaskMinionJobStatus.created},
                )

    async def __check_job_returns(self, task_job: TaskJob, jid: JID) -> None:
        task: TaskModel = await self.get_task()
        job_returns: list[JobResult] = await self.job_service.get_job_all_returns(jid)
        now = utc_now()

        for job_return in job_returns:
            minion_id: str = job_return.id
            master: str = job_return.salt_master
            minion_key: str = self.__get_minion_key(master=master, minion_id=minion_id)
            returns_status = task_job.returns_statuses.get(minion_id, TaskJobReturnStatus.waiting)

            if returns_status != TaskJobReturnStatus.waiting:
                continue

            task.minions[minion_key].finished_dt = now

            if job_return.success is True:
                task_job.returns_statuses[minion_id] = TaskJobReturnStatus.succeeded
                task.minions[minion_key].status = TaskMinionStatus.success
                task.minions[minion_key].jobs[task_job.jid] = TaskMinionJobStatus.success
            else:
                task_job.returns_statuses[minion_id] = TaskJobReturnStatus.failed
                task.minions[minion_key].jobs[task_job.jid] = TaskMinionJobStatus.failed
                if len(task.minions[minion_key].jobs) >= task.max_retries:
                    task.minions[minion_key].status = TaskMinionStatus.failed
                else:
                    task.minions[minion_key].status = TaskMinionStatus.pending

    @staticmethod
    async def __update_task_job_status(task_job: TaskJob) -> None:
        has_failed: bool = False
        has_not_finished: bool = False

        for returns_status in task_job.returns_statuses.values():
            if returns_status not in [
                TaskJobReturnStatus.succeeded.value,
                TaskJobReturnStatus.failed.value,
                TaskJobReturnStatus.timeout.value,
            ]:
                has_not_finished = True

            if returns_status in [TaskJobReturnStatus.failed, TaskJobReturnStatus.timeout]:
                has_failed = True

        if not has_not_finished:
            task_job.finished_dt = utc_now()

            if has_failed:
                task_job.status = TaskJobStatus.failed
            else:
                task_job.status = TaskJobStatus.succeeded

    async def process(self) -> None:
        task: TaskModel = await self.get_task()

        if task.status not in [TaskStatus.running, TaskStatus.stopping]:
            return

        if not task.minions and task.status == TaskStatus.running:
            await self.__fill_minions_by_targeting()
        else:
            await self.__check_jobs()

            if task.status == TaskStatus.running:
                await self.__create_jobs()

        for job in task.jobs.values():
            if job.status in [TaskJobStatus.pending, TaskJobStatus.running]:
                break
        else:
            task.status = TaskStatus.stopped if task.status == TaskStatus.stopping else TaskStatus.finished

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
