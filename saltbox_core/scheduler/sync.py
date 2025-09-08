import json
from typing import Any

import anyio

from saltbox_core.event_bus.rabbit.common_messages import SyncTemplatesResponseEventBusMessage
from saltbox_sdk.config.logger_config import logger
from saltbox_sdk.event_bus.utils import send_message


async def sync_scheduler_templates() -> None:
    templates: list[dict[str, Any]] = []

    async for template_path in anyio.Path(__file__).parent.joinpath('templates').glob('*.json'):
        logger.debug(f'Loading template: {template_path}')

        async with await template_path.open('r') as f:
            templates.append(json.loads(await f.read()))

    logger.debug(f'Found templates: {[template['fun'] for template in templates]}')

    logger.debug(f'Syncing {len(templates)} templates ')
    for template in templates:
        await send_message(
            message=SyncTemplatesResponseEventBusMessage.model_validate(
                {
                    'target': 'scheduler',
                    'task_target': template.get('target', 'core'),
                    'fun': template['fun'],
                    'name': template['name'],
                    'json_schema': template.get('json_schema', {}),
                    'ui_schema': template.get('ui_schema', {}),
                }
            ),
            queue='scheduler_send_template',
        )
    logger.debug(f'Finished syncing {len(templates)} templates')
