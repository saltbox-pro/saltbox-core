from typing import Any

from redis import Redis

from celery.exceptions import SoftTimeLimitExceeded
from salt_box_core.celery import celery
from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.config import get_sync_mongo_db
from salt_box_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema, JobSchemaUpdateSchema
from salt_box_core.settings.tasks import git_operations_task
from salt_box_core.utilities.git_repo_helper import GitRepoService, RepositoryLocker


# TODO (a.baikov): Refactor this task later
@celery.task(
    bind=True,
    name='sync_schemas_repo_task',
    time_limit=60,
    soft_time_limit=30,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
)
def sync_schemas_repo_task(self: Any, repo_url: str) -> dict:
    db = None
    locker = None

    try:
        db = get_sync_mongo_db()
        collection = db.get_collection('job_schemas')
        logger.debug('sync_schemas_repo_task')

        # lock reo
        redis = Redis.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)
        locker = RepositoryLocker(redis)
        if locker.is_locked(repo_url):
            msg = 'Another task is running for the same repo'
            logger.debug(msg)
            raise Exception(msg)

        locker.acquire_lock(repo_url)
        logger.debug('Repo locked')

        git_result = git_operations_task.apply_async(
            kwargs={
                'repo_url': repo_url,
                'local_name': SETTINGS.salt_func_local_repo_name,
            },
            expires=20,
        ).get(timeout=20)

        if not git_result['status'] == 'success':
            msg = 'Git operation failed'
            raise Exception(msg)

        repo = GitRepoService(
            repo_url=repo_url,
            local_name=SETTINGS.salt_func_local_repo_name,
        )

        logger.debug('Try to parse schemas')
        schemas, errors = repo.parse_schemas()

        parsed_schema_names = [schema['name'] for schema in schemas]
        removed_count = collection.delete_many({'name': {'$nin': parsed_schema_names}})

        created = []
        updated = []
        for schema in schemas:
            existing_schema = collection.find_one({'name': schema['name']})

            if not existing_schema:
                logger.debug('Try create: %s', schema['name'])
                schema_create_obj = JobSchemaCreateSchema(**schema)
                collection.insert_one(schema_create_obj.model_dump())
                created.append(schema_create_obj.name)
            elif existing_schema['commit_hash'] != schema['commit_hash']:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = JobSchemaUpdateSchema(**schema)
                collection.update_one({'name': schema['name']}, {'$set': schema_update_obj.model_dump()})
                updated.append(schema_update_obj.name)

        return {
            'created': created,
            'updated': updated,
            'removed_count': removed_count.deleted_count,
            'errors': errors,
        }
    except SoftTimeLimitExceeded:
        logger.error('Task exceeded time limit')
        raise

    except Exception as e:
        msg = f'Error during task execution: {e!s}'
        logger.error(msg)
        raise

    finally:
        if locker:
            locker.release_lock(repo_url)
            logger.debug('Repo unlocked')
