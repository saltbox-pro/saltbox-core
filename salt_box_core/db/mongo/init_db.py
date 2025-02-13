import pymongo

from salt_box_core.config import logger
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.minion_collections.repositories.collection_repository import CollectionRepository
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionCreateSchema
from salt_box_core.schema_sync.repository import JSONSchemaRepository


async def init_json_schemas() -> None:
    db = get_mongo_db()
    json_schemas_repo = JSONSchemaRepository(db)

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
    logger.info('MongoDB collections initialized')

    # Initialize json_schemas collection
    await init_json_schemas()
    logger.info('JSON schemas initialized')
