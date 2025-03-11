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
from salt_box_core.jobs.tasks import sync_schemas_repo_task
from salt_box_core.utilities.git_repo_helper import GitRepoService
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
            path = Path(SETTINGS.local_repos_path) / SETTINGS.salt_func_local_repo_name
            logger.debug('Remove folder: %s', path)
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

    async def sync(self) -> str:
        logger.debug('Start task: %s', SETTINGS.salt_func_repo_url)
        task = sync_schemas_repo_task.delay(SETTINGS.salt_func_repo_url)
        logger.debug('task: %s', task)
        return task.id

    async def sync_old(self) -> dict:
        git_repo = GitRepoService(SETTINGS.salt_func_repo_url)
        try:
            await asyncio.wait_for(asyncio.to_thread(git_repo.clone_or_pull), timeout=30)
        except TimeoutError:
            msg = 'Timeout error while cloning or pulling git repo'
            logger.error(msg)
            raise TimeoutError(msg) from None
        schemas, errors = git_repo.parse_schemas()
        parsed_schema_names = [schema['name'] for schema in schemas]
        removed_count = await self.repo.delete_many({'name': {'$nin': parsed_schema_names}})

        created = []
        updated = []
        for schema in schemas:
            try:
                existing_schema = await self.get_by_name(schema['name'])
            except ObjectNotFoundError:
                existing_schema = None

            if not existing_schema:
                logger.debug('Try create: %s', schema['name'])
                schema_create_obj = JobSchemaCreateSchema(**schema)
                await self.create(schema_create_obj)
                created.append(schema_create_obj.name)
            elif existing_schema.commit_hash != schema['commit_hash']:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = JobSchemaUpdateSchema(**schema)
                await self.update({'name': schema['name']}, schema_update_obj)
                updated.append(schema_update_obj.name)

        return {
            'created': created,
            'updated': updated,
            'removed_count': removed_count,
            'errors': errors,
        }


def get_job_schema_service(
    repo: Annotated[JobSchemaRepository, Depends(get_job_schema_repository)],
) -> JobSchemaService:
    return JobSchemaService(repo)
