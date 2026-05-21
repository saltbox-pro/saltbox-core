from typing import Any

from redis.asyncio import Redis
from taskiq import TaskiqDepends
from taskiq.depends.progress_tracker import ProgressTracker, TaskState

from saltbox_core.config import Settings, logger
from saltbox_core.task_templates.exceptions import TaskTemplateSourceLockException
from saltbox_core.task_templates.utils.orchestrator import SyncOrchestrator, get_sync_orchestrator
from saltbox_core.tkq import broker, queue_default

# from saltbox_core.tkq import ConcurrencyLocker
from saltbox_core.utilities.redis_locker import AsyncRedisLockFactory
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import get_redis

SETTINGS = Settings()


@broker.task(queue_name=queue_default.name)
async def source_discover_task(
    source_id: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    orchestrator: SyncOrchestrator = TaskiqDepends(get_sync_orchestrator),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict[str, Any]:
    lock_factory = AsyncRedisLockFactory(rdb=redis, ttl=60, prefix='template_source')
    lock = lock_factory.create(source_id)
    logger.info('is_locked: %s', await lock.locked())

    if await lock.locked():
        msg = f'Source {source_id} is already being fetched by another task.'
        logger.warning(msg)
        raise TaskTemplateSourceLockException(source_id=source_id)

    async with lock:
        await progress.set_progress(TaskState.STARTED, 'Fetch started')
        try:
            await orchestrator.discover(PyObjectId(source_id))
            await progress.set_progress(TaskState.SUCCESS, 'Fetch successful')
            return {'status': 'discovered'}
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Fetch failed')
            raise


@broker.task(queue_name=queue_default.name)
async def source_prepare_task(
    source_id: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    orchestrator: SyncOrchestrator = TaskiqDepends(get_sync_orchestrator),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict[str, Any]:
    lock_factory = AsyncRedisLockFactory(rdb=redis, ttl=60, prefix='template_source')
    lock = lock_factory.create(source_id)
    logger.info('is_locked: %s', await lock.locked())

    if await lock.locked():
        msg = f'Source {source_id} is already being fetched by another task.'
        logger.warning(msg)
        raise TaskTemplateSourceLockException(source_id=source_id)

    async with lock:
        await progress.set_progress(TaskState.STARTED, 'Prepare started')
        try:
            await orchestrator.prepare(PyObjectId(source_id))
            await progress.set_progress(TaskState.SUCCESS, 'Prepare successful')
            return {'status': 'prepared'}
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Prepare failed')
            raise


@broker.task(queue_name=queue_default.name)
async def source_sync_task(
    source_id: str,
    master_ids: list[str],
    progress: ProgressTracker[Any] = TaskiqDepends(),
    orchestrator: SyncOrchestrator = TaskiqDepends(get_sync_orchestrator),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict[str, Any]:
    lock_factory = AsyncRedisLockFactory(rdb=redis, ttl=60, prefix='template_source')
    lock = lock_factory.create(source_id)
    logger.info('is_locked: %s', await lock.locked())

    if await lock.locked():
        msg = f'Source {source_id} is already being fetched by another task.'
        logger.warning(msg)
        raise TaskTemplateSourceLockException(source_id=source_id)

    async with lock:
        await progress.set_progress(TaskState.STARTED, 'Sync started')
        try:
            await orchestrator.prepare(PyObjectId(source_id))
            await progress.set_progress(TaskState.SUCCESS, 'Prepare successful')
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Prepare failed')
            raise

        try:
            await orchestrator.sync(PyObjectId(source_id), [PyObjectId(m_id) for m_id in master_ids])
            await progress.set_progress(TaskState.SUCCESS, 'Sync successful')
            return {'status': 'synced'}
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Sync failed')
            raise


@broker.task(queue_name=queue_default.name)
async def source_remove_task(
    source_id: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    orchestrator: SyncOrchestrator = TaskiqDepends(get_sync_orchestrator),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict[str, Any]:
    lock_factory = AsyncRedisLockFactory(rdb=redis, ttl=60, prefix='template_source')
    lock = lock_factory.create(source_id)
    logger.info('is_locked: %s', await lock.locked())

    if await lock.locked():
        msg = f'Source {source_id} is already being fetched by another task.'
        logger.warning(msg)
        raise TaskTemplateSourceLockException(source_id=source_id)

    async with lock:
        await progress.set_progress(TaskState.STARTED, 'Remove started')
        try:
            await orchestrator.remove(PyObjectId(source_id))
            await progress.set_progress(TaskState.SUCCESS, 'Remove successful')
            return {'status': 'removed'}
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Remove failed')
            raise


@broker.task(queue_name=queue_default.name)
async def create_tpl_from_raw_task(
    source_id: str,
    file_name: str,
    content: str,
    progress: ProgressTracker[Any] = TaskiqDepends(),
    orchestrator: SyncOrchestrator = TaskiqDepends(get_sync_orchestrator),
    redis: Redis = TaskiqDepends(get_redis),
) -> dict[str, Any]:
    lock_factory = AsyncRedisLockFactory(rdb=redis, ttl=60, prefix='template_source')
    lock = lock_factory.create(source_id)
    logger.info('is_locked: %s', await lock.locked())

    if await lock.locked():
        msg = f'Source {source_id} is already being fetched by another task.'
        logger.warning(msg)
        raise TaskTemplateSourceLockException(source_id=source_id)

    async with lock:
        await progress.set_progress(TaskState.STARTED, 'Create template from raw started')
        try:
            await orchestrator.create_template_from_raw(PyObjectId(source_id), file_name, content)
            await progress.set_progress(TaskState.SUCCESS, 'Create template from raw successful')
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Create template from raw failed')
            raise

        try:
            await orchestrator.discover(PyObjectId(source_id))
            await progress.set_progress(TaskState.SUCCESS, 'Fetch successful')
        except Exception:
            await progress.set_progress(TaskState.FAILURE, 'Fetch failed')
            raise

    return {'status': 'created'}
