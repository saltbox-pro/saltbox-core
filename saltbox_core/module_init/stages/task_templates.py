from saltbox_core.config import logger
from saltbox_core.masters.repositories.master_repository import get_master_repository
from saltbox_core.masters.services.master_service import get_master_service
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
from saltbox_core.task_templates.schemas.source import SourceType, TemplateSourceCreateLocalSchema
from saltbox_core.task_templates.services.source import get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import get_sshfs_file_service
from saltbox_core.task_templates.services.template import get_task_tpl_service
from saltbox_core.task_templates.utils.manifest import get_sshfs_sync
from saltbox_core.task_templates.utils.orchestrator import get_sync_orchestrator
from saltbox_core.tasks.repositories.task import get_task_repository
from saltbox_core.tasks.repositories.tasks_minion import get_task_minion_repository
from saltbox_core.tasks.repositories.tasks_status import get_task_status_repository
from saltbox_core.tasks.services.task import get_task_service
from saltbox_core.tasks.services.tasks_minion import get_task_minion_service
from saltbox_core.tasks.services.tasks_status import get_task_status_service
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.redis.config import get_redis_now
from saltbox_sdk.exceptions import ObjectNotFoundException


async def run_stage() -> None:
    logger.info('Initializing task template sources...')
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
    master_repo = get_master_repository(db)

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
    master_service = get_master_service(repo=master_repo)

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

    is_base_local_exists = await tpl_source_service.exists({'source_type': SourceType.LOCAL_BUNDLE})
    created_id: PyObjectId | None = None
    if not is_base_local_exists:
        logger.info('Creating base local template source...')
        source_in = TemplateSourceCreateLocalSchema(
            name='Local templates',
            description='Built-in source for storing user configuration templates.',
            namespace='baselocal',
        )

        created_id = await tpl_source_service.create_local(source_in)

        logger.info('Base local template source created with id %s. Discovering...', created_id)
    else:
        logger.info('Base local template source already exists. Skipping creation.')

    try:
        default_local = await tpl_source_service.get(
            {'source_type': SourceType.LOCAL_BUNDLE, 'name': 'Local templates'}
        )
        created_id = default_local.id
    except ObjectNotFoundException:
        created_id = None
    if created_id:
        orchestrator = await get_sync_orchestrator(
            source_service=tpl_source_service,
            template_service=template_service,
            sshfs_file_service=file_service,
            pillar_service=pillar_service,
            master_service=master_service,
            sshfs_sync_service=sshfs_sync_service,
        )
        await orchestrator.discover(created_id)
