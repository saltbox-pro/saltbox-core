import pymongo

from fastms_core.config import logger
from fastms_core.minion_collections.repository import CollectionRepository
from fastms_core.minion_collections.schemas.collection_schemas import MinionCollectionCreateSchema


async def init_collections() -> None:
    collections_repo = CollectionRepository()

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
        obj = MinionCollectionCreateSchema(
            title='Root collection',
            slug='root',
            query={},
        )
        await collections_repo.add(obj)
        logger.debug('MinionCollection with slug `root` created')


async def init_mongo_db() -> None:
    """Initialize MongoDB collections"""

    # Initialize minion_collections collection
    await init_collections()
    logger.info('MongoDB collections initialized')
