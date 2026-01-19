from anyio import Path

from saltbox_core.config import logger
from saltbox_sdk.scheduler.handler import sync_scheduler_templates


async def sync_templates() -> None:
    path = Path(__file__).parent.joinpath('scheduler/templates')

    logger.info(f'Loading scheduler templates from directory: {path}')

    await sync_scheduler_templates(templates_path=path, service_name='core')
