import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PyObjectId
from salt_box_core.schema_sync.schemas import JSONSchemaSyncResponse
from salt_box_core.schema_sync.services.schema_sync_service import SchemaGitRepoService
from salt_box_core.sls_repos.repository import (
    SettingsSlsRepoRepository,
    get_sls_repo_repository,
)
from salt_box_core.sls_repos.schemas.settings_schemas import (
    SettingsSlsRepoCreateSchema,
    SettingsSlsRepoModel,
    SettingsSlsRepoUpdateSchema,
)
from salt_box_core.tasks.schemas.task_template_schemas import TaskTemplateCreateSchema, TaskTemplateUpdateSchema
from salt_box_core.tasks.services.tasks_templates import TaskTemplateService
from salt_box_core.utilities.serivces.mongo_base_service import MongoBaseService


class SettingsSlsRepoService(
    MongoBaseService[
        SettingsSlsRepoRepository, SettingsSlsRepoModel, SettingsSlsRepoCreateSchema, SettingsSlsRepoUpdateSchema
    ]
):
    async def activate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if document.is_active:
            return document

        return await self.update(query=sid, data={'is_active': True})

    async def deactivate(self, sid: PyObjectId) -> SettingsSlsRepoModel:
        document = await self.get(sid)
        if not document.is_active:
            return document
        return await self.update(query=sid, data={'is_active': False})

    async def sync_all(self) -> None:
        # get all active repos
        # for each repo call self.sync in celery task
        # return task id
        pass

    async def delete_and_clean(self, sid: PyObjectId, tpl_service: TaskTemplateService) -> None:
        repo_settings = await self.get(sid)
        # Remove all templates from this repo
        try:
            deleted_count = await tpl_service.delete_many({'repo_id': sid})
            logger.debug('deleted_count: %s', deleted_count)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

        try:
            path = './' / Path(SETTINGS.local_repos_path) / repo_settings.local_path
            logger.debug('Remove folder: %s', path)
            if path.exists():
                await asyncio.to_thread(shutil.rmtree, path)
        except Exception as e:
            msg = f'{e!s}'
            logger.error(msg)
            raise

        await self.delete(sid)

    async def sync(self, sid: PyObjectId, sls_tpl_service: TaskTemplateService) -> JSONSchemaSyncResponse:
        repo_settings = await self.get(sid)
        git_repo = SchemaGitRepoService(
            repo_url=repo_settings.repo_url.unicode_string(),
            local_name=repo_settings.local_path,
            login=repo_settings.repo_user,
            token=repo_settings.repo_pass.get_secret_value() if repo_settings.repo_pass else None,
        )

        try:
            await asyncio.wait_for(asyncio.to_thread(git_repo.clone_or_pull), timeout=30)
        except TimeoutError:
            msg = 'Timeout error while cloning or pulling git repo'
            logger.error(msg)
            update_data = {'last_synced': datetime.now(UTC), 'is_last_sync_successful': False, 'last_sync_error': msg}
            await self.update(sid, update_data)
            raise TimeoutError(msg) from None
        except Exception as e:
            msg = f'{e!s}'
            update_data = {'last_synced': datetime.now(UTC), 'is_last_sync_successful': False, 'last_sync_error': msg}
            await self.update(sid, update_data)
            raise

        # parse schemas from sls
        schemas, errors = await git_repo.extract_schema_from_sls()
        logger.debug('errors: %s', errors)

        # save templates
        parsed_schema_names = [schema['name'] for schema in schemas]
        logger.debug('parsed_schema_names: %s', parsed_schema_names)

        query = {
            '$and': [
                {'repo_id': sid},
                {'name': {'$nin': parsed_schema_names}},
            ],
        }
        removed_count = await sls_tpl_service.delete_many(query)
        logger.debug('removed_count: %s', removed_count)

        created = []
        updated = []
        for schema in schemas:
            try:
                existing_schema = await sls_tpl_service.get_by_name(schema['name'], sid)
            except ObjectNotFoundError:
                existing_schema = None

            if not existing_schema:
                logger.debug('Try create: %s', schema['name'])
                schema_create_obj = TaskTemplateCreateSchema(**schema, repo_id=sid)
                await sls_tpl_service.create(schema_create_obj)
                created.append(schema_create_obj.name)
            elif existing_schema.commit_hash != schema['commit_hash'] and existing_schema.repo_id == sid:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = TaskTemplateUpdateSchema(**schema)
                await sls_tpl_service.update({'name': schema['name']}, schema_update_obj)
                updated.append(schema_update_obj.name)

        update_data = {
            'last_synced': datetime.now(UTC),
            'is_last_sync_successful': True,
        }
        await self.update(sid, update_data)

        return JSONSchemaSyncResponse(
            created=created,
            updated=updated,
            removed_count=removed_count,
            errors=errors,
        )


def get_sls_repo_service(
    repo: Annotated[SettingsSlsRepoRepository, Depends(get_sls_repo_repository)],
) -> SettingsSlsRepoService:
    return SettingsSlsRepoService(repo)
