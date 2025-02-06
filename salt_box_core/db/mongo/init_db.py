import pymongo

from salt_box_core.config import logger
from salt_box_core.db.mongo.config import get_mongo_db
from salt_box_core.minion_collections.repositories.collection_repository import CollectionRepository
from salt_box_core.minion_collections.schemas.collection_schemas import CollectionCreateSchema


async def init_collections() -> None:
    db = get_mongo_db()
    collections_repo = CollectionRepository(db)

    # Check existing indexes
    indexes = sorted(await collections_repo.collection.index_information())

    # Create unique index for slug if not exists
    if 'slug_unique_index_text' not in indexes:
        result = await collections_repo.collection.create_index(
            [('slug', pymongo.TEXT)], name='slug_unique_index_text', unique=True
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
