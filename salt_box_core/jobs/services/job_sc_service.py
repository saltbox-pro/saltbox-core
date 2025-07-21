import asyncio
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from salt_box_core.jobs.schemas.job_sc_schemas import (
    JobSchemaCreateSchema,
    JobSchemaModel,
    JobSchemaUpdateSchema,
)
from salt_box_core.jobs.tasks import job_schemas_sync_task
from salt_box_core.utilities.json_schema import Draft4ValidatorWithDefaults
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class JobSchemaService(
    MongoBaseService[JobSchemaRepository, JobSchemaModel, JobSchemaCreateSchema, JobSchemaUpdateSchema]
):
    async def get_by_name(self, name: str) -> JobSchemaModel:
        return await self.repo.get({'name': name})

    async def get_validated_data(self, name: str, data: dict) -> dict:
        try:
            json_schema = await self.get_by_name(name)
        except ObjectNotFoundError:
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
            logger.error(msg)
            raise

    async def sync(self) -> str:
        logger.debug('Start task: %s', SETTINGS.salt_func_repo_url)
        task = await job_schemas_sync_task.kiq(repo_url=SETTINGS.salt_func_repo_url)
        logger.debug('task: %s', task)
        return task.task_id


def get_job_schema_service(
    repo: Annotated[JobSchemaRepository, Depends(get_job_schema_repository)],
) -> JobSchemaService:
    return JobSchemaService(repo)
