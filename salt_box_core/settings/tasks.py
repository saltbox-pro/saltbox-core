from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from redis import Redis

from celery.exceptions import SoftTimeLimitExceeded
from salt_box_core.celery import celery
from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.mongo.config import get_sync_mongo_db
from salt_box_core.tasks.schemas.task_template_schemas import TaskTemplateCreateSchema, TaskTemplateUpdateSchema
from salt_box_core.utilities.git_repo_helper import GitRepoService, RepositoryLocker


@celery.task(bind=True, name='git_operations_task', time_limit=20, soft_time_limit=10)
def git_operations_task(
    self: Any, repo_url: str, local_name: str, login: str | None = None, token: str | None = None
) -> dict:
    try:
        git_repo = GitRepoService(repo_url=repo_url, local_name=local_name, login=login, token=token)
        git_repo.clone_or_pull()
        return {'status': 'success', 'repo_path': str(git_repo.local_path)}
    except SoftTimeLimitExceeded:
        logger.error('Git operation timed out')
        raise
    except Exception as e:
        logger.error(f'Git operation failed: {e!s}')
        raise


# TODO (a.baikov): Refactor this task later
@celery.task(
    bind=True,
    name='sync_sls_repo_task',
    time_limit=60,
    soft_time_limit=30,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 5},
)
def sync_sls_repo_task(self: Any, repo_id: str) -> dict:
    db = None
    git_repo = None
    locker = None

    try:
        db = get_sync_mongo_db()
        settings_collection = db.get_collection('settings_sls_repos')
        tpl_collection = db.get_collection('task_templates')

        repo_obj = settings_collection.find_one({'_id': ObjectId(repo_id)})
        if not repo_obj:
            msg = f'Repo with id {repo_id} not found'
            logger.error(msg)
            raise Exception(msg)

        logger.debug('sync_sls_repo_task')

        redis = Redis.from_url(SETTINGS.redis_url, **SETTINGS.redis_connection_kwargs)
        locker = RepositoryLocker(redis)
        if locker.is_locked(repo_obj['repo_url']):
            msg = 'Another task is running for the same repo'
            logger.debug(msg)
            raise Exception(msg)

        locker.acquire_lock(repo_obj['repo_url'])
        logger.debug('Repo locked')

        git_result = git_operations_task.apply_async(
            kwargs={
                'repo_url': repo_obj['repo_url'],
                'local_name': repo_obj['local_path'],
                'login': repo_obj['repo_user'],
                'token': repo_obj['repo_pass'],
            },
            expires=20,  # Таймаут для подзадачи
        ).get(timeout=20)  # Ждем результат не более 20 секунд

        if git_result['status'] != 'success':
            msg = 'Git operation failed'
            raise Exception(msg)

        git_repo = GitRepoService(
            repo_url=repo_obj['repo_url'],
            local_name=repo_obj['local_path'],
            login=repo_obj['repo_user'],
            token=repo_obj['repo_pass'],
        )

        # parse schemas from sls
        schemas, errors = git_repo.extract_schema_from_sls()
        logger.debug('errors: %s', errors)

        # save templates
        parsed_schema_names = [schema['name'] for schema in schemas]
        logger.debug('parsed_schema_names: %s', parsed_schema_names)

        # remove old templates
        sid = repo_obj['_id']
        logger.debug('sid: %s', sid)
        query = {
            '$and': [
                {'repo_id': sid},
                {'name': {'$nin': parsed_schema_names}},
            ],
        }
        removed = tpl_collection.delete_many(query)
        logger.debug('removed_count: %s', removed.deleted_count)

        created = []
        updated = []
        for schema in schemas:
            existing_schema = tpl_collection.find_one({'name': schema['name'], 'repo_id': sid})

            if not existing_schema:
                logger.debug('Try create: %s', schema['name'])
                schema_create_obj = TaskTemplateCreateSchema(**schema, repo_id=sid)
                tpl_collection.insert_one(schema_create_obj.model_dump())
                created.append(schema_create_obj.name)
            elif existing_schema['commit_hash'] != schema['commit_hash'] and existing_schema.repo_id == sid:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = TaskTemplateUpdateSchema(**schema)
                tpl_collection.update_one({'name': schema['name']}, {'$set': schema_update_obj.model_dump()})
                updated.append(schema_update_obj.name)

        update_data = {
            'last_synced': datetime.now(UTC),
            'is_last_sync_successful': True,
            'last_sync_error': '',
        }
        settings_collection.update_one({'_id': ObjectId(repo_id)}, {'$set': update_data})

        return {
            'created': created,
            'updated': updated,
            'removed_count': removed.deleted_count,
            'errors': errors,
        }

    except SoftTimeLimitExceeded:
        logger.error('Task exceeded time limit')
        update_data = {
            'last_synced': datetime.now(UTC),
            'is_last_sync_successful': False,
            'last_sync_error': 'Task exceeded time limit',
        }
        settings_collection.update_one({'_id': ObjectId(repo_id)}, {'$set': update_data})
        raise

    except Exception as e:
        msg = f'Error during task execution: {e!s}'
        logger.error(msg)
        update_data = {'last_synced': datetime.now(UTC), 'is_last_sync_successful': False, 'last_sync_error': msg}
        settings_collection.update_one({'_id': ObjectId(repo_id)}, {'$set': update_data})
        raise

    finally:
        if locker and repo_obj:
            locker.release_lock(repo_obj['repo_url'])
            logger.debug('Repo unlocked')
