from typing import Any

from redis.asyncio import Redis
from taskiq import TaskiqDepends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import ObjectNotFoundError
from salt_box_core.db.redis.config import get_redis_dep
from salt_box_core.jobs.repositories.job_sc_repository import JobSchemaRepository, get_job_schema_repository
from salt_box_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema, JobSchemaUpdateSchema
from salt_box_core.tkq import broker
from salt_box_core.utilities.git_repo_helper import GitRepoService, MultipleRepoSyncError, repository_lock


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
        except ObjectNotFoundError:
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
            updated.append(schema_update_obj.name)

    return created, updated, removed_count


# TODO (a.baikov): Deal with retries
@broker.task(timeout=30, retry_on_error=True, _retries=3)
async def job_schemas_sync_task(
    repo_url: str,
    repo: JobSchemaRepository = TaskiqDepends(get_job_schema_repository),
    redis: Redis = TaskiqDepends(get_redis_dep),
) -> dict:
    """Task for synchronizing job schemas from a Git repository."""
    try:
        async with repository_lock(redis, repo_url):
            git_repo = GitRepoService(repo_url=repo_url, local_name=SETTINGS.salt_func_local_repo_name)
            git_repo.clone_or_pull()
            logger.debug('Repo cloned or pulled')

            logger.debug('Try to parse schemas')
            schemas, errors = git_repo.parse_schemas()
            parsed_schema_names = [schema['name'] for schema in schemas]

            created, updated, removed_count = await sync_schemas(repo, schemas, parsed_schema_names)

            return {
                'created': created,
                'updated': updated,
                'removed_count': removed_count,
                'errors': errors,
            }

    except MultipleRepoSyncError as e:
        msg = f'Multiple repo sync error: {e!s}'
        logger.debug(msg)
        return {
            'status': 'error',
            'message': msg,
        }
    except Exception as e:
        msg = f'Error during task execution: {e!s}'
        logger.error(msg)
        raise
