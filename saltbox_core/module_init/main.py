import asyncio

from saltbox_core.config import logger
from saltbox_core.module_init.stages.db import run_stage as run_stage_db
from saltbox_core.module_init.stages.pre_init import run_stage as run_stage_pre_init
from saltbox_core.module_init.stages.scheduler import run_stage as run_stage_scheduler
from saltbox_core.module_init.stages.task_templates import run_stage as run_stage_task_templates


async def async_main() -> None:
    logger.info('Starting Core initialization...')

    stages = [
        run_stage_pre_init,
        run_stage_db,
        run_stage_scheduler,
        run_stage_task_templates,
    ]
    for stage in stages:
        await stage()

    logger.info('Core initialization has been completed successfully')


def main() -> None:
    asyncio.run(async_main())


if __name__ == '__main__':
    main()
