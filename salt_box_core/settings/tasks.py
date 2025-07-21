import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from redis.asyncio import Redis
from taskiq import TaskiqDepends
from taskiq.depends.progress_tracker import ProgressTracker, TaskState

from salt_box_core.config import Settings, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.redis.config import get_redis_dep
from salt_box_core.event_bus.masters_bus import notify_accepted_masters_on_repos_update
from salt_box_core.settings.repository import SettingsSlsRepoRepository, get_sls_repo_repository
from salt_box_core.tasks.repositories.task_template_repository import (
    TaskTemplateRepository,
    get_task_template_repository,
)
from salt_box_core.tasks.schemas.task_template_schemas import TaskTemplateCreateSchema, TaskTemplateUpdateSchema
from salt_box_core.tkq import ConcurrencyLocker, broker
from salt_box_core.utilities.git_repo_helper import (
    GitRepoService,
    SlsRepo,
    SlsReposServeUpdater,
    create_sshfs_sync,
    repository_lock,
)

SETTINGS = Settings()
SYNC_SERVE_DIR_LOCK_EXPIRATION_SEC = 300


async def sync_schemas(
    sls_repo_id: ObjectId, repo: TaskTemplateRepository, schemas: list[dict[str, Any]], parsed_schema_names: list[str]
) -> tuple[list[str], list[str], int]:
    """Synchronizes schemas with the database."""
    # remove old templates
    logger.debug('sid: %s', sls_repo_id)
    query = {
        '$and': [
            {'repo_id': sls_repo_id},
            {'name': {'$nin': parsed_schema_names}},
        ],
    }
    removed_count = await repo.delete_many(query)
    logger.debug('removed_count: %s', removed_count)

    created = []
    updated = []

    for schema in schemas:
        try:
            existing_schema = await repo.get({'name': schema['name'], 'repo_id': sls_repo_id})
        except ObjectNotFoundError:
            existing_schema = None

        if not existing_schema:
            logger.debug('Try create: %s', schema['name'])
            schema_create_obj = TaskTemplateCreateSchema(**schema, repo_id=sls_repo_id)
            await repo.create(schema_create_obj)
            created.append(schema_create_obj.name)
        elif existing_schema.commit_hash != schema['commit_hash'] and existing_schema.repo_id == sls_repo_id:
            logger.debug('Try update: %s', schema['name'])
            schema_update_obj = TaskTemplateUpdateSchema(**schema, repo_id=sls_repo_id)
            await repo.update(
                {'name': schema['name']},
                schema_update_obj,
            )
            updated.append(schema_update_obj.name)

    return created, updated, removed_count


# TODO (a.baikov): Deal with retries and timeouts
# If we set timeout, rabbitmq will be waiting for acks for this time. After restart worker try to
# re-execute task, but locker in redis not released (it has ttl=timeout).
@broker.task(timeout=SETTINGS.local_repo_sync_timeout_sec, retry_on_error=True, _retries=3)
async def sync_sls_repo_task(
    repo_id: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    repo: TaskTemplateRepository = TaskiqDepends(get_task_template_repository),
    sls_repo_model: SettingsSlsRepoRepository = TaskiqDepends(get_sls_repo_repository),
    redis: Redis = TaskiqDepends(get_redis_dep),
) -> dict:
    """Task for synchronizing job schemas from a Git repository."""
    try:
        await progress.set_progress(TaskState.STARTED, 'Sync started')
        repo_obj = await sls_repo_model.get({'_id': ObjectId(repo_id)})
        url = repo_obj.repo_url if isinstance(repo_obj.repo_url, str) else os.fspath(repo_obj.repo_url)
        async with repository_lock(redis, url):
            git_repo = GitRepoService(
                repo_url=url,
                local_name=repo_obj.local_path,
                login=repo_obj.repo_user,
                token=repo_obj.repo_pass.get_secret_value() if repo_obj.repo_pass else None,
            )
            sls_repo = SlsRepo(repo=git_repo)
            logger.debug('Try to clone or pull repo with to_thread: %s', url)

            await asyncio.wait_for(
                asyncio.to_thread(git_repo.clone_or_pull),
                timeout=SETTINGS.local_repo_sync_timeout_sec,
            )
            logger.debug('Repo cloned or pulled')

            manifest = repo_obj.parse_manifest()
            for file_path, file_entry in manifest.sshfs_files.items():
                await create_sshfs_sync(file_path, file_entry).sync()

            logger.debug('Try to parse schemas')
            schemas, errors = sls_repo.extract_schema_from_sls()
            parsed_schema_names = [schema['name'] for schema in schemas]

            created, updated, removed_count = await sync_schemas(repo_obj.id, repo, schemas, parsed_schema_names)

            update_data = {
                'root': str(manifest.root),
                'last_synced': datetime.now(UTC),
                'is_last_sync_successful': True,
                'last_sync_error': '\n'.join(errors) if errors else '',
            }
            await sls_repo_model.update({'_id': ObjectId(repo_id)}, update_data)

            sync_serve_task = await sync_sls_repos_to_serve_dir.kiq()
            await sync_serve_task.wait_result()

            await progress.set_progress(TaskState.SUCCESS, 'Sync successful')

            return {
                'created': created,
                'updated': updated,
                'removed_count': removed_count,
                'errors': errors,
            }
    except Exception as e:
        msg = f'Error during task execution: {e!s}'
        logger.error(msg)
        await sls_repo_model.update(
            {'_id': ObjectId(repo_id)},
            {
                'last_synced': datetime.now(UTC),
                'last_sync_error': msg,
                'is_last_sync_successful': False,
            },
        )
        await progress.set_progress(TaskState.FAILURE, msg)
        raise


@broker.task()
async def sync_sls_repos_to_serve_dir(
    sls_repo_model: SettingsSlsRepoRepository = TaskiqDepends(get_sls_repo_repository),
    limiter: None = TaskiqDepends(ConcurrencyLocker(expire=SYNC_SERVE_DIR_LOCK_EXPIRATION_SEC)),
) -> None:
    active_repos = await sls_repo_model.get_list(query={'is_active': True}, skip=0, limit=0)
    salt_modules_serve_updater = SlsReposServeUpdater(active_repos)
    salt_modules_serve_updater.update()
    await notify_accepted_masters_on_repos_update()
