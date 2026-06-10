from typing import Annotated, Any

from fastapi import Depends
from typing_extensions import overload, override

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_schemas import JobCreateSchema
from saltbox_core.jobs.services.job_services import JobService, get_job_service
from saltbox_core.minion_collections.repositories.extra_data_collector import (
    ExtraDataCollectorRepository,
    get_extra_data_collector_repository,
)
from saltbox_core.minion_collections.schemas.extra_data_collector import (
    ExtraDataCollectorCreateSchema,
    ExtraDataCollectorLaunchType,
    ExtraDataCollectorModel,
    ExtraDataCollectorUpdateSchema,
)
from saltbox_core.minion_collections.services.extra_data_category import (
    ExtraDataCategoryService,
    get_extra_data_category_service,
)
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.tasks.schemas.task import TaskCreateInputSchema
from saltbox_core.tasks.services.task import TaskService, get_task_service
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId
from saltbox_sdk.db.schemas_base import Source, UserShort
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class ExtraDataCollectorService(
    MongoBaseService[
        ExtraDataCollectorRepository,
        ExtraDataCollectorModel,
        ExtraDataCollectorCreateSchema,
        ExtraDataCollectorUpdateSchema,
    ]
):
    def __init__(
        self,
        repo: ExtraDataCollectorRepository,
        extra_data_category_service: ExtraDataCategoryService,
        minion_service: MinionService,
        job_service: JobService,
        task_service: TaskService,
    ):
        super().__init__(repo)
        self.extra_data_category_service = extra_data_category_service
        self.minion_service = minion_service
        self.job_service = job_service
        self.task_service = task_service

    async def _run_job(self, launch_data: dict[str, Any], user: UserShort, source: Source) -> tuple[str, PyObjectId]:
        job_id = await self.job_service.create(
            data=JobCreateSchema.model_validate(
                {**launch_data, 'user': user, 'source': source},
            )
        )

        return 'job', job_id

    async def _run_task(self, launch_data: dict[str, Any], user: UserShort, source: Source) -> tuple[str, PyObjectId]:
        task_id = await self.task_service.create(
            data=TaskCreateInputSchema.model_validate(
                {**launch_data, 'user': user, 'source': source},
            )
        )

        return 'task', task_id

    async def run(self, collector_id: PyObjectId, launch_data: dict[str, Any]) -> tuple[str, Any]:
        collector = await self.get(collector_id)

        merged_launch_data = {**collector.launch_default_data}
        merged_launch_data.update(launch_data)
        source = Source(type='extra_collector', id=str(collector.id))

        run_callback = {ExtraDataCollectorLaunchType.job: self._run_job}.get(collector.launch_type)

        if run_callback is None:
            msg = 'Unknown launch type'
            raise RuntimeError(msg)

        return await run_callback(launch_data=merged_launch_data, user=collector.user, source=source)

    @overload
    async def process_data(self, *, minion_id: str, salt_master: str, collector_id: PyObjectId, data: Any) -> None: ...

    @overload
    async def process_data(self, *, minion_id: PyObjectId, collector_id: PyObjectId, data: Any) -> None: ...

    async def process_data(
        self, *, minion_id: str | PyObjectId, salt_master: str | None = None, collector_id: PyObjectId, data: Any
    ) -> None:
        if not await self.exists(query={'_id': collector_id, 'is_enabled': True}):
            msg = 'Collector does not exist or not enabled'
            raise RuntimeError(msg)

        try:
            if isinstance(minion_id, str) and salt_master:
                minion = await self.minion_service.get(
                    query={'minion_id': minion_id, 'master': salt_master}, projection_model=EmptyModel
                )
            elif isinstance(minion_id, PyObjectId):
                minion = await self.minion_service.get(minion_id, projection_model=EmptyModel)
            else:
                msg_0 = 'Invalid minion id'
                raise RuntimeError(msg_0)
        except ObjectNotFoundException as e:
            msg = f'Minion id not found: {e}'
            logger.error(msg)
            return

        await self.extra_data_category_service.process_data(minion_id=minion.id, collector_id=collector_id, data=data)


def get_extra_data_collector_service(
    repo: Annotated[ExtraDataCollectorRepository, Depends(get_extra_data_collector_repository)],
    extra_data_category_service: Annotated[ExtraDataCategoryService, Depends(get_extra_data_category_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    job_service: Annotated[JobService, Depends(get_job_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> ExtraDataCollectorService:
    return ExtraDataCollectorService(
        repo=repo,
        extra_data_category_service=extra_data_category_service,
        minion_service=minion_service,
        job_service=job_service,
        task_service=task_service,
    )
