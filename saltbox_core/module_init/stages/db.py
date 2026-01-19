from saltbox_core.config import logger
from saltbox_core.db.init_mongo_db import init_mongo_db


async def run_migrations() -> None:
    logger.info('Running DB migrations...')


async def run_stage() -> None:
    logger.info('Initializing DB...')

    await init_mongo_db()
    await run_migrations()
