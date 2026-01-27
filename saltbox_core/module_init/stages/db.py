import anyio

from saltbox_core.config import logger
from saltbox_core.db.init_mongo_db import init_mongo_db
from saltbox_core.db.migration_repo import get_mongo_migration_repository
from saltbox_sdk.db.mongo.config import get_mongo_db
from saltbox_sdk.db.redis.config import get_redis_now
from saltbox_sdk.serivces.migration_service import MigrationService


async def run_migrations() -> None:

    mongo_db = get_mongo_db()
    redis_db = get_redis_now()
    mongo_migration_repo = get_mongo_migration_repository(mongo_db)

    migration_service = MigrationService(mongo_migration_repo, redis_db)

    # migrations_root_path = anyio.Path(__file__).parent.parent.parent.parent  # NOTE: include test migrations
    migrations_root_path = anyio.Path(__file__).parent.parent.parent
    await migration_service.execute_migrations(migrations_root_path)


async def run_stage() -> None:

    logger.info('Running initialization of MongoDB collections')
    await init_mongo_db()

    logger.info('Running DB migrations...')
    await run_migrations()
