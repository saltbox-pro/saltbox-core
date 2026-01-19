from saltbox_core.config import logger
from saltbox_core.scheduler.utils import sync_templates


async def run_stage() -> None:
    logger.info('Initializing scheduler...')

    await sync_templates()
