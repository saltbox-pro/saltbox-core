import json

import anyio
import pymongo

from saltbox_core.config import logger
from saltbox_core.jobs.repositories.job_sc_repository import JobSchemaRepository
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema
from saltbox_core.masters.repositories.master_repository import MasterRepository
from saltbox_core.minion_collections.repositories.collection_repository import CollectionRepository
from saltbox_core.minion_collections.schemas.collection_schemas import CollectionCreateSchema
from saltbox_core.settings.repository import SettingsSlsRepoRepository
from saltbox_core.tasks.repositories.task_template_repository import TaskTemplateRepository
from saltbox_sdk.db.mongo.config import get_mongo_db


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

    # Create unique index for local_path if not exists
    if 'local_path_unique_index_asc' not in indexes:
        result = await sls_settings_repo.collection.create_index(
            [('local_path', pymongo.ASCENDING)], name='local_path_unique_index_asc', unique=True
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

    is_default_schema_exists = await json_schemas_repo.exists(query={'name': 'default'})

    if not is_default_schema_exists:
        logger.debug('Creating default schema')

        async with await anyio.open_file('./saltbox_core/jobs/default_func_schema.json') as f:
            default_schema = json.loads(await f.read())

        async with await anyio.open_file('./saltbox_core/jobs/default_func_ui_schema.json') as f:
            default_ui_schema = json.loads(await f.read())

        default_schema = await json_schemas_repo.create(
            data=JobSchemaCreateSchema.model_validate(
                {'name': 'default', 'json_schema': default_schema, 'ui_schema': default_ui_schema, 'commit_hash': ''}
            )
        )

        logger.info('Created default schema: %s', default_schema)
    else:
        logger.debug('Default schema already exists')


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
            owner='system',
        )
        await collections_repo.create(obj)
        logger.debug('MinionCollection with slug `root` created')


async def init_masters() -> None:
    db = get_mongo_db()
    masters_repo = MasterRepository(db)

    # Check existing indexes
    indexes = sorted(await masters_repo.collection.index_information())

    # Create unique index for master_id if not exists
    if 'master_id_unique_index_asc' not in indexes:
        result = await masters_repo.collection.create_index(
            [('master_id', pymongo.ASCENDING)], name='master_id_unique_index_asc', unique=True
        )
        logger.debug('Index created: %s', result)

    logger.debug('Indexes: %s', indexes)


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

    # Initialize masters collection
    await init_masters()
    logger.debug('Masters initialized')
