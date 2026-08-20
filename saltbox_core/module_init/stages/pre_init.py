from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.collection import get_collection_repository
from saltbox_core.minion_collections.repositories.extra_data import get_extra_data_repository
from saltbox_core.minion_collections.repositories.extra_data_category import get_extra_data_category_repository
from saltbox_core.minion_collections.repositories.minion import get_minion_repository
from saltbox_core.minion_collections.services.collection import get_collection_service
from saltbox_core.minion_collections.services.minion import get_minion_service
from saltbox_core.pillars.repository import get_pillar_repository
from saltbox_core.pillars.services.pillar import get_pillar_service
from saltbox_core.pillars.services.pillar_crypto import get_pillar_crypto_service
from saltbox_core.task_templates.repositories.source import get_template_source_repository
from saltbox_core.task_templates.repositories.sshfs_file import get_sshfs_file_repository
from saltbox_core.task_templates.repositories.template import get_task_template_repository
from saltbox_core.task_templates.schemas.source import SourceType
from saltbox_core.task_templates.services.source import get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import get_sshfs_file_service
from saltbox_core.task_templates.services.template import get_task_tpl_service
from saltbox_core.task_templates.utils.manifest import get_sshfs_sync
from saltbox_core.tasks.repositories.task import get_task_repository
from saltbox_core.tasks.repositories.tasks_minion import get_task_minion_repository
from saltbox_core.tasks.repositories.tasks_status import get_task_status_repository
from saltbox_core.tasks.services.task import get_task_service
from saltbox_core.tasks.services.tasks_minion import get_task_minion_service
from saltbox_core.tasks.services.tasks_status import get_task_status_service
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import EmptyModel
from saltbox_sdk.db.redis.config import get_redis_now


async def fix_task_template_empty_namespaces() -> None:
    logger.info('Fixing task template empty namespaces...')

    db = get_mongo_db()
    tpl_source_repo = get_template_source_repository(db)

    updated_ids = await tpl_source_repo.bulk_update(
        query={'namespace': ''},
        data={'namespace': None},
    )

    logger.info(
        'Blank task template namespace set to None: %s documents changed',
        len(updated_ids),
    )


async def remove_local_sources_without_namespace() -> None:
    logger.info('Removing local sources without namespace...')
    db = get_mongo_db()
    rdb = get_redis_now()

    tpl_source_repo = get_template_source_repository(db)
    tpl_repo = get_task_template_repository(db)
    pillar_repo = get_pillar_repository(db)
    file_repo = get_sshfs_file_repository(db)
    task_repo = get_task_repository(db)
    task_status_repo = get_task_status_repository(db)
    task_minion_repo = get_task_minion_repository(db)
    collection_repo = get_collection_repository(db)
    extra_data_category_repo = get_extra_data_category_repository(db)
    minion_extra_data_repo = get_extra_data_repository(db, extra_data_category_repo)
    minion_repo = get_minion_repository(db, minion_extra_data_repo)

    sshfs_sync_service = await get_sshfs_sync()
    template_service = get_task_tpl_service(tpl_repo, pillar_repo)
    file_service = get_sshfs_file_service(repo=file_repo, sshfs_sync_service=sshfs_sync_service)
    task_status_service = get_task_status_service(repo=task_status_repo)
    task_minion_service = get_task_minion_service(repo=task_minion_repo, rdb=rdb)
    collections_service = get_collection_service(repo=collection_repo)
    minion_service = get_minion_service(repo=minion_repo)
    crypto_service = get_pillar_crypto_service()
    pillar_service = get_pillar_service(
        repo=pillar_repo,
        minion_service=minion_service,
        collection_service=collections_service,
        crypto_service=crypto_service,
    )

    task_template_service = get_task_tpl_service(repo=tpl_repo, pillar_repo=pillar_repo)

    task_service = get_task_service(
        repo=task_repo,
        rdb=rdb,
        task_status_service=task_status_service,
        task_template_service=task_template_service,
        task_minion_service=task_minion_service,
        collections_service=collections_service,
        minion_service=minion_service,
        pillar_service=pillar_service,
    )
    tpl_source_service = get_tpl_source_service(
        repo=tpl_source_repo, template_service=template_service, file_service=file_service, task_service=task_service
    )

    sources_to_delete = await tpl_source_service.get_list(
        query={'namespace': None, 'source_type': SourceType.LOCAL_BUNDLE},
        projection_model=EmptyModel,
    )
    for source in sources_to_delete:
        await tpl_source_service.delete(query=source.id)

    logger.info(
        'Local sources without namespace cleanup completed: %s documents deleted',
        len(sources_to_delete),
    )


async def run_stage() -> None:
    logger.info('Pre-initializing Fixies...')
    await fix_task_template_empty_namespaces()
    await remove_local_sources_without_namespace()
