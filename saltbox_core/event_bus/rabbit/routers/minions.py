from faststream import Logger
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo

from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.minion_collections.services.minion_extra_data import MinionExtraDataItemService
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel
from saltbox_sdk.event_bus.schemas import (
    MinionAddOrUpdateExtraDataRequestMessage,
    MinionRemoveExtraDataRequestMessage,
)

router = RabbitRouter(prefix='minions_')


@router.subscriber('add_extra_data')
async def add_extra_data(
    message: MinionAddOrUpdateExtraDataRequestMessage, context: ContextRepo, logger: Logger
) -> None:
    if message.target != 'core':
        return None

    minion_service: MinionService = context.get('minion_service')
    minion_extra_data_item_service: MinionExtraDataItemService = context.get('minion_extra_data_item_service')

    data_items = [
        await minion_extra_data_item_service.get_or_create(
            source=message.sender, name=message.category_name, value=value, projection_model=EmptyModel
        )
        for value in message.values
    ]

    await minion_service.update(
        query={'minion_id': message.minion_id, 'master': message.master},
        data={
            '_extra': {'$each': [data_item.id for data_item in data_items]},
        },
        operator=MongoUpdateOperator.add_to_set,
    )

    return None


@router.subscriber('remove_extra_data')
async def remove_extra_data(message: MinionRemoveExtraDataRequestMessage, context: ContextRepo, logger: Logger) -> None:
    if message.target != 'core':
        return None

    minion_service: MinionService = context.get('minion_service')

    await minion_service.update(
        query={'minion_id': message.minion_id, 'master': message.master},
        data={f'_extra.{message.sender}.{message.category_name}': 1},
        operator=MongoUpdateOperator.unset,
    )

    return None
