from saltbox_core.config import logger
from saltbox_core.db.init_mongo_db import init_mongo_db
from saltbox_sdk.migrations.migrator import Migrator


async def run_migrations() -> None:
    logger.info('Running DB migrations...')

    migrator = Migrator(
        modules_paths=[
            ['saltbox_core', 'jobs'],
            ['saltbox_core', 'masters'],
            ['saltbox_core', 'minion_collections'],
            ['saltbox_core', 'pillars'],
            ['saltbox_core', 'settings'],
            ['saltbox_core', 'task_templates'],
            ['saltbox_core', 'tasks'],
        ]
    )
    await migrator.migrate()


async def run_stage() -> None:
    logger.info('Initializing DB...')

    await init_mongo_db()
    await run_migrations()
