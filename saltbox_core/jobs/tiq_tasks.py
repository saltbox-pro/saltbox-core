import asyncio
from typing import Any

from redis.asyncio import Redis
from taskiq import TaskiqDepends
from taskiq.depends.progress_tracker import ProgressTracker, TaskState

from saltbox_core.config import SETTINGS, logger
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema, JobSchemaUpdateSchema
from saltbox_core.tkq import broker, queue_default
from saltbox_core.utilities.git_repo_helper import GitRepoService, parse_schemas, repository_lock
from saltbox_sdk.db.redis.config import get_redis
from saltbox_sdk.exceptions import ObjectNotFoundException, TaskiqException, TaskiqTimeoutException


async def sync_schemas(
    repo: JobSchemaRepository, schemas: list[dict[str, Any]], parsed_schema_names: list[str]
) -> tuple[list[str], list[str], int]:
    """Synchronizes schemas with the database."""
    removed_count = await repo.delete_many({'name': {'$nin': parsed_schema_names}})
    created = []
    updated = []

    for schema in schemas:
        try:
            existing_schema = await repo.get({'name': schema['name']})
        except ObjectNotFoundException:
            existing_schema = None

        if not existing_schema:
            logger.debug('Try create: %s', schema['name'])
            schema_create_obj = JobSchemaCreateSchema(**schema)
            await repo.create(schema_create_obj)
            created.append(schema_create_obj.name)
        elif existing_schema.commit_hash != schema['commit_hash']:
            logger.debug('Try update: %s', schema['name'])
            schema_update_obj = JobSchemaUpdateSchema(**schema)
            await repo.update(
                {'name': schema['name']},
                schema_update_obj,
            )
            updated.append(schema['name'])

    return created, updated, removed_count


# TODO (a.baikov): Deal with retries
@broker.task(queue_name=queue_default.name, timeout=30, retry_on_error=True, _retries=3)
async def job_schemas_sync_task(
    repo_url: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    repo: JobSchemaRepository = TaskiqDepends(get_job_schema_repository),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict:
    """Task for synchronizing job schemas from a Git repository."""
    try:
        await progress.set_progress(TaskState.STARTED, 'Sync started')
        async with repository_lock(redis, repo_url):
            git_repo = GitRepoService(repo_url=repo_url, local_name=SETTINGS.salt_func_local_repo_name)
            await asyncio.wait_for(
                asyncio.to_thread(git_repo.clone_or_pull),
                timeout=SETTINGS.local_repo_sync_timeout_sec,
            )
            logger.debug('Repo cloned or pulled')

            logger.debug('Try to parse schemas')
            schemas, errors = parse_schemas(git_repo)
            parsed_schema_names = [schema['name'] for schema in schemas]

            created, updated, removed_count = await sync_schemas(repo, schemas, parsed_schema_names)
            await progress.set_progress(TaskState.SUCCESS, 'Sync successful')

            return {
                'created': created,
                'updated': updated,
                'removed_count': removed_count,
                'errors': errors,
            }
    except TimeoutError:
        msg = 'Timeout while trying to clone or pull the repository'
        await progress.set_progress(TaskState.FAILURE, msg)
        raise TaskiqTimeoutException(msg) from None
    except Exception as e:
        msg = f'Error during task execution: {e!s}'
        await progress.set_progress(TaskState.FAILURE, msg)
        raise TaskiqException(msg) from e
