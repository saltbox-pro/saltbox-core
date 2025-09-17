from typing import Annotated, Any

from fastapi import Depends
from redis.asyncio import Redis

from saltbox_core.config import logger
from saltbox_core.jobs.exceptions import JobCreateException, JobDoesNotExistsException
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema, JobModel
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.services.collection_service import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion_service import MinionService, get_minion_service
from saltbox_core.tasks.exceptions import TaskServiceException
from saltbox_core.tasks.schemas.task_schemas import (
    TaskCreateInputSchema,
    TaskJob,
    TaskJobReturnStatus,
    TaskJobStatus,
    TaskJobTarget,
    TaskJobTargetType,
    TaskMinion,
    TaskMinionJobStatus,
    TaskMinionStatus,
    TaskModel,
    TaskPostProcessingType,
    TaskSource,
    TaskStatus,
    TaskUpdateSchema,
)
from saltbox_core.tasks.services.tasks import TaskService, get_task_service
from saltbox_core.utilities.jid import JID
from saltbox_core.utilities.mongo_query_to_salt_tgt_converter import MongoQueryToSaltTgtConverter
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import MultipleObjectsFoundException, ObjectNotFoundException
from saltbox_sdk.fastapi_utils.dependencies import RedisDependency
from saltbox_sdk.utilities.helpers import utc_now


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

        for attr, value in kwargs.items():
            task.__setattr__(attr, value)

        self.__task = await self.task_service.update(
            query=task.id,
            data=TaskUpdateSchema.model_validate(task.model_dump(exclude=set('id'))),
            notify=notify,
        )

        return self.__task

    async def run(self, force: bool = False) -> None:
        task = await self.get_task()

        if task.status in [TaskStatus.created, TaskStatus.stopped] or force:
            await self.update_task(status=TaskStatus.running)

            if task.source and task.source.type == 'task' and task.source.id:
                try:
                    parent_task = await self.task_service.get(PyObjectId(task.source.id))

                    await self.task_service.update(
                        query=parent_task.id,
                        data={
                            **TaskUpdateSchema.model_validate(parent_task.model_dump(exclude=set('id'))).model_dump(
                                by_alias=True
                            ),
                            'status': TaskStatus.running,
                        },
                    )
                except ObjectNotFoundException:
                    await self.update_task(sourse__id=None)

    async def __stop_jobs(self) -> None:
        task = await self.get_task()

        for jid in task.jobs.keys():
            await self.job_service.stop_job(JID(jid))

    async def stop(self) -> None:
        task = await self.get_task()

        if task.status == TaskStatus.running:
            await self.__stop_jobs()
            await self.update_task(status=TaskStatus.stopping)

    async def restart_failed(self) -> None:
        task = await self.get_task()

        if task.status == TaskStatus.finished:
            for minion in task.minions.values():
                if minion.status == TaskMinionStatus.failed:
                    minion.status = TaskMinionStatus.pending

            await self.__create_jobs(ignore_limits=True)
            await self.run(force=True)

    async def restart_failed_on_minion(self, master: str, minion_id: str) -> None:
        task = await self.get_task()
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
        task = await self.get_task()
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
        task = await self.get_task()
        collection = await self.collection_service.get(task.target_collection.id)
        sub_queries: list[dict] = [collection.full_query] if collection.full_query else []

        if task.target_query:
            sub_queries.append(task.target_query)
        if task.target_minions:
            sub_queries.append(
                {
                    '$or': [
                        {'minion_id': minion_target.minion_id, 'master': minion_target.master}
                        for minion_target in task.target_minions
                    ]
                }
            )

        if len(sub_queries) > 1:
            query = {'$and': sub_queries}
        elif len(sub_queries) == 0:
            query = {}
        else:
            query = sub_queries[0]

        return query

    async def __fill_minions_by_targeting(self) -> None:
        task = await self.get_task()
        targeting_query = await self.__get__targeting_query()
        not_compound_compatible_query = self.__check_compound_compatible_query(targeting_query)
        minions = await self.minion_service.get_list(query=targeting_query, limit=0, skip=0)
        minions_by_master: dict[str, list[str]] = {}

        for minion in minions:
            if minion.master in task.target_masters or not len(task.target_masters):
                task.minions[self.__get_minion_key(minion.master, minion.minion_id)] = TaskMinion(
                    id=minion.id,
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
        task = await self.get_task()
        tgt = compound if compound else ','.join(minions)
        tgt_type = TaskJobTargetType.compound if compound else TaskJobTargetType.list

        job = await self.job_service.create(
            JobCreateSchema.model_validate(
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

        task.jobs[str(job.jid)] = TaskJob(
            jid=str(job.jid),
            target=TaskJobTarget(tgt=tgt, tgt_type=tgt_type, master=master),
            minions_by_targeting=minions,
        )

        for minion_id in minions:
            minion = task.minions[self.__get_minion_key(master=master, minion_id=minion_id)]

            minion.status = TaskMinionStatus.in_work
            minion.jobs[str(job.jid)] = TaskMinionJobStatus.created
            minion.start_last_dt = task.jobs[str(job.jid)].created_dt

    async def __create_jobs(self, ignore_limits: bool = True) -> None:
        task = await self.get_task()
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
                except JobCreateException as e:
                    msg = f'Creating job failed for task {task.id}:\n{e}'
                    logger.info(msg)
                    continue

    async def __check_jobs(self) -> None:
        task = await self.get_task()

        for task_job in task.jobs.values():
            if task_job.status in [TaskJobStatus.failed, TaskJobStatus.succeeded]:
                continue

            try:
                job_data = await self.job_service.get_job(JID(task_job.jid))

            except JobDoesNotExistsException:
                task_job.status = TaskJobStatus.failed
                continue

            if job_data.status == JobModel.JobStatus.in_queue:
                continue

            if not task_job.minions_from_salt:
                task_job.minions_from_salt = job_data.minions
                await self.__check_minions_in_job(task_job=task_job, job_data=job_data)

            await self.__check_job_returns(task_job=task_job, jid=JID(task_job.jid))
            await self.__update_task_job_status(task_job=task_job)

    async def __check_minions_in_job(self, task_job: TaskJob, job_data: JobModel) -> None:
        task = await self.get_task()

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

            try:
                minion_obj = await self.minion_service.get({'minion_id': minion_id, 'master': task_job.target.master})
            except ObjectNotFoundException:
                minion_obj = None
            except MultipleObjectsFoundException:
                logger.error('Multiple minion objects returned')
                continue

            if minion_key not in task.minions.keys():
                task.minions[minion_key] = TaskMinion(
                    id=minion_obj.id if minion_obj else None,
                    minion_id=minion_id,
                    master=task_job.target.master,
                    jobs={task_job.jid: TaskMinionJobStatus.created},
                )

    async def __check_job_returns(self, task_job: TaskJob, jid: JID) -> None:
        task = await self.get_task()
        job_returns = await self.job_service.get_job_all_returns(jid)
        now = utc_now()

        for job_return in job_returns:
            minion_id = job_return.id
            master = job_return.salt_master
            minion_key = self.__get_minion_key(master=master, minion_id=minion_id)
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

    async def __postprocessing(self) -> None:  # noqa: C901
        task = await self.get_task()

        if not task.postprocessing:
            return

        if not task.postprocessing_dt:
            task.postprocessing_dt = utc_now()

        if task.postprocessing.type == TaskPostProcessingType.on_success:
            for task_minion in task.minions.values():
                if task_minion.status != TaskMinionStatus.success:
                    task.status = TaskStatus.finished
                    return

        if task.postprocessing.wait_minions:
            for minion_data in task.postprocessing.wait_minions:
                try:
                    minion = await self.minion_service.get_by_master_and_id(
                        master=minion_data.master, minion_id=minion_data.minion_id
                    )
                except ObjectNotFoundException:
                    return

                if not minion.last_activity:
                    return

                if minion.last_activity < task.postprocessing_dt:
                    return

        if task.postprocessing.notify:
            # TODO (i.moshkov): notify user
            task.postprocessing.notify_dt = utc_now()

        if task.postprocessing.task_create_request:
            if not task.postprocessing.task_create_id:
                created_task = await self.task_service.create(
                    TaskCreateInputSchema.model_validate(
                        {
                            **task.postprocessing.task_create_request.model_dump(by_alias=True),
                            'user': task.user,
                            'source': TaskSource.model_validate({'type': 'task', 'id': task.id}),
                        }
                    )
                )
                await self.task_service.update(
                    query=created_task.id,
                    data=TaskUpdateSchema.model_validate({**created_task.model_dump(), 'status': TaskStatus.running}),
                )
                task.postprocessing.task_create_id = created_task.id

                return
            else:
                try:
                    children_task = await self.task_service.get(task.postprocessing.task_create_id)
                except ObjectNotFoundException:
                    task.postprocessing.task_create_id = None
                    return

                if children_task.status == TaskStatus.stopped:
                    task.status = TaskStatus.stopped
                    return

                if children_task.status == TaskStatus.finished:
                    task.status = TaskStatus.finished
        else:
            task.status = TaskStatus.finished

    async def process(self) -> None:
        task = await self.get_task()

        if task.status not in [TaskStatus.running, TaskStatus.stopping, TaskStatus.postprocessing]:
            return

        if not task.minions and task.status == TaskStatus.running:
            await self.__fill_minions_by_targeting()
        elif task.status in [TaskStatus.running, TaskStatus.stopping]:
            await self.__check_jobs()

            if task.status == TaskStatus.running:
                await self.__create_jobs()

            for job in task.jobs.values():
                if job.status in [TaskJobStatus.pending, TaskJobStatus.running]:
                    break
            else:
                if task.status == TaskStatus.stopping:
                    task.status = TaskStatus.stopped
                elif task.postprocessing:
                    task.status = TaskStatus.postprocessing
                else:
                    task.status = TaskStatus.finished
        elif task.status == TaskStatus.postprocessing:
            await self.__postprocessing()

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
