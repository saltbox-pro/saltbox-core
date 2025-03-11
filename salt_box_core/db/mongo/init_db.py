import pymongo

from salt_box_core.config import logger
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from salt_box_core.minion_collections.repositories.collection_repository import CollectionRepository
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionCreateSchema
from salt_box_core.settings.repository import SettingsSlsRepoRepository
from salt_box_core.tasks.repositories.task_template_repository import TaskTemplateRepository


async def init_task_tpl() -> None:
    db = get_mongo_db()
    sls_tpl_repo = TaskTemplateRepository(db)

    # Check existing indexes
    indexes = sorted(await sls_tpl_repo.collection.index_information())

    # Create unique index for name and repo_id if not exists
    if 'name_repo_id_unique_index' not in indexes:
        result = await sls_tpl_repo.collection.create_index(
            [('name', pymongo.ASCENDING), ('repo_id', pymongo.ASCENDING)], name='name_repo_id_unique_index', unique=True
        )
        logger.debug('Index created: %s', result)
        logger.debug('Indexes: %s', indexes)


async def init_sls_repos_settings() -> None:
    db = get_mongo_db()
    sls_settings_repo = SettingsSlsRepoRepository(db)

    # Check existing indexes
    indexes = sorted(await sls_settings_repo.collection.index_information())

    # Create unique index for name if not exists
    if 'name_unique_index_asc' not in indexes:
        result = await sls_settings_repo.collection.create_index(
            [('repo_url', pymongo.ASCENDING)], name='url_unique_index_asc', unique=True
        )
        logger.debug('Index created: %s', result)
        logger.debug('Indexes: %s', indexes)


async def init_job_schemas() -> None:
    db = get_mongo_db()
    json_schemas_repo = JobSchemaRepository(db)

    # Check existing indexes
    indexes = sorted(await json_schemas_repo.collection.index_information())

    # Create unique index for name if not exists
    if 'name_unique_index_asc' not in indexes:
        result = await json_schemas_repo.collection.create_index(
            [('name', pymongo.ASCENDING)], name='name_unique_index_asc', unique=True
        )
        logger.debug('Index created: %s', result)
        logger.debug('Indexes: %s', indexes)


async def init_collections() -> None:
    db = get_mongo_db()
    collections_repo = CollectionRepository(db)

    # Check existing indexes
    indexes = sorted(await collections_repo.collection.index_information())

    # Create unique index for slug if not exists
    if 'slug_unique_index_asc' not in indexes:
        result = await collections_repo.collection.create_index(
            [('slug', pymongo.ASCENDING)], name='slug_unique_index_asc', unique=True
        )
        logger.debug('Index created: %s', result)
        logger.debug('Indexes: %s', indexes)

    # Create root collection if not exists
    root_collection_exist = await collections_repo.collection.count_documents({'slug': 'root'})
    if not root_collection_exist:
        logger.debug("MinionCollection with slug `root` doesn't exist... Creating...")
        obj = CollectionCreateSchema(
            title='Root collection',
            slug='root',
            query={},
        )
        await collections_repo.create(obj)
        logger.debug('MinionCollection with slug `root` created')


async def init_mongo_db() -> None:
    """Initialize MongoDB collections"""

    # Initialize minion_collections collection
    await init_collections()
    logger.debug('MongoDB collections initialized')

    # Initialize json_schemas collection
    await init_job_schemas()
    logger.debug('Job schemas initialized')

    # Initialize sls_repos_settings collection
    await init_sls_repos_settings()
    logger.debug('SLS repos settings initialized')

    # Initialize sls_tpl collection
    await init_task_tpl()
    logger.debug('SLS templates initialized')
