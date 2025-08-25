import asyncio
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from saltbox_core.config import SETTINGS, logger
from saltbox_core.jobs.exceptions import JobException
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from saltbox_core.jobs.schemas.job_sc_schemas import (
    JobSchemaCreateSchema,
    JobSchemaModel,
    JobSchemaUpdateSchema,
)
from saltbox_core.jobs.tasks import job_schemas_sync_task
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.utilities.json_schema import Draft4ValidatorWithDefaults


class JobSchemaService(
    MongoBaseService[JobSchemaRepository, JobSchemaModel, JobSchemaCreateSchema, JobSchemaUpdateSchema]
):
    async def get_by_name(self, name: str) -> JobSchemaModel:
        return await self.repo.get({'name': name})

    async def get_validated_data(self, name: str, data: dict) -> dict:
        try:
            json_schema = await self.get_by_name(name)
        except ObjectNotFoundException:
            json_schema = await self.get_by_name('default')

        Draft4ValidatorWithDefaults(json_schema.json_schema).validate(data)

        return data

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
        logger.debug('Start task: %s', SETTINGS.salt_func_repo_url)
        task = await job_schemas_sync_task.kiq(repo_url=SETTINGS.salt_func_repo_url)
        logger.debug('task: %s', task)
        return task.task_id


def get_job_schema_service(
    repo: Annotated[JobSchemaRepository, Depends(get_job_schema_repository)],
) -> JobSchemaService:
    return JobSchemaService(repo)
