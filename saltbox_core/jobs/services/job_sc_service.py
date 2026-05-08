import asyncio
import shutil
from pathlib import Path
from typing import Annotated, overload

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.config import SETTINGS, logger
from saltbox_core.jobs.exceptions import JobException
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from saltbox_core.jobs.schemas.job_sc_schemas import (
    JobSchemaCreateSchema,
    JobSchemaJSONSchemaOnlySchema,
    JobSchemaModel,
    JobSchemaTTLOnlySchema,
    JobSchemaUpdateSchema,
)
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel
from saltbox_sdk.utilities.json_schema import Draft4ValidatorWithDefaults


class JobSchemaService(
    MongoBaseService[JobSchemaRepository, JobSchemaModel, JobSchemaCreateSchema, JobSchemaUpdateSchema]
):
    @overload
    async def get_by_name(
        self,
        name: str,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> JobSchemaModel: ...

    @overload
    async def get_by_name(
        self,
        name: str,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def get_by_name(
        self,
        name: str,
        *,
        session: MongoAsyncClientSession | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> JobSchemaModel | ProjectionModel:
        query = {'name': name}

        if projection_model:
            return await self.repo.get(query=query, session=session, projection_model=projection_model)

        return await self.repo.get(query=query, session=session)

    async def get_validated_data(self, name: str, data: dict, session: MongoAsyncClientSession | None = None) -> dict:
        try:
            json_schema = await self.get_by_name(
                name=name, session=session, projection_model=JobSchemaJSONSchemaOnlySchema
            )
        except ObjectNotFoundException:
            json_schema = await self.get_by_name(
                name='default', session=session, projection_model=JobSchemaJSONSchemaOnlySchema
            )

        Draft4ValidatorWithDefaults(json_schema.json_schema).validate(data)

        return data

    async def get_ttl(self, name: str, session: MongoAsyncClientSession | None = None) -> int:
        try:
            json_schema = await self.get_by_name(name=name, session=session, projection_model=JobSchemaTTLOnlySchema)
        except ObjectNotFoundException:
            return SETTINGS.jobs_default_ttl

        if json_schema.default_ttl is None:
            return SETTINGS.jobs_default_ttl
        elif json_schema.default_ttl == 0:
            return SETTINGS.jobs_max_ttl
        else:
            return json_schema.default_ttl

    async def remove_repo_data(self) -> None:
        try:
            path = Path(SETTINGS.local_repos_dir) / SETTINGS.salt_func_local_repo_name
            logger.debug('Remove folder: %s', path)
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            msg = f'{e!s}'
            raise JobException(msg) from None

    async def sync(self) -> str:
        from saltbox_core.jobs.tiq_tasks import job_schemas_sync_task

        logger.debug('Start task: %s', SETTINGS.salt_func_repo_url)
        task = await job_schemas_sync_task.kiq(repo_url=SETTINGS.salt_func_repo_url)
        logger.debug('task: %s', task)
        return task.task_id


def get_job_schema_service(
    repo: Annotated[JobSchemaRepository, Depends(get_job_schema_repository)],
) -> JobSchemaService:
    return JobSchemaService(repo)
