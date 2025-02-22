import asyncio
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.schema_sync.repository import JSONSchemaRepository, get_json_schema_repository
from salt_box_core.schema_sync.schemas import (
    JSONSchemaCreateSchema,
    JSONSchemaModel,
    JSONSchemaSyncResponse,
    JSONSchemaUpdateSchema,
)
from salt_box_core.schema_sync.services.schema_sync_service import SchemaGitRepoService
from salt_box_core.utilities.json_schema import Draft4ValidatorWithDefaults
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class JSONSchemaService(
    MongoBaseService[JSONSchemaRepository, JSONSchemaModel, JSONSchemaCreateSchema, JSONSchemaUpdateSchema]
):
    async def get_by_name(self, name: str) -> JSONSchemaModel:
        return await self.repo.get({'name': name})

    async def get_validated_data(self, name: str, data: dict) -> dict:
        try:
            json_schema = await self.get_by_name(name)
        except ObjectNotFoundError:
            json_schema = await self.get_by_name('default')

        Draft4ValidatorWithDefaults(json_schema.json_schema).validate(data)

        return data

    async def remove_repo_data(self) -> None:
        path = Path(SETTINGS.local_repos_path) / SETTINGS.salt_func_local_repo_name
        if path.exists():
            logger.debug('Remove repo data from %s', path)
            for item in path.iterdir():
                if item.is_dir():
                    await asyncio.to_thread(shutil.rmtree, item)
                else:
                    await asyncio.to_thread(item.unlink)

    async def sync(self) -> JSONSchemaSyncResponse:
        git_repo = SchemaGitRepoService(SETTINGS.salt_func_repo_url)
        try:
            await asyncio.wait_for(asyncio.to_thread(git_repo.clone_or_pull), timeout=30)
        except TimeoutError:
            msg = 'Timeout error while cloning or pulling git repo'
            logger.error(msg)
            raise TimeoutError(msg) from None
        schemas, errors = await git_repo.parse_schemas()
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
                schema_create_obj = JSONSchemaCreateSchema(**schema)
                await self.create(schema_create_obj)
                created.append(schema_create_obj.name)
            elif existing_schema.commit_hash != schema['commit_hash']:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = JSONSchemaUpdateSchema(**schema)
                await self.update({'name': schema['name']}, schema_update_obj)
                updated.append(schema_update_obj.name)

        return JSONSchemaSyncResponse(
            created=created,
            updated=updated,
            removed_count=removed_count,
            errors=errors,
        )


def get_json_schema_service(
    repo: Annotated[JSONSchemaRepository, Depends(get_json_schema_repository)],
) -> JSONSchemaService:
    return JSONSchemaService(repo)
