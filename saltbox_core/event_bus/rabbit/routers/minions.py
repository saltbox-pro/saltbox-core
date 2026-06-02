from typing import Any

from faststream import Logger
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo, RabbitMessage

from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel
from saltbox_sdk.event_bus.schemas import (
    MinionAddOrUpdateExtraDataRequestMessage,
    MinionExtraDataType,
    MinionRemoveExtraDataRequestMessage,
)
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.utilities.helpers import utc_now

router = RabbitRouter(prefix='minions_')


@router.subscriber('add_extra_data')
async def add_extra_data(
    message: MinionAddOrUpdateExtraDataRequestMessage, msg: RabbitMessage, context: ContextRepo, logger: Logger
) -> None:
    if message.target != 'core':
        return None

    await msg.ack()

    minion_service: MinionService = context.get('minion_service')
    extra_data_service: ExtraDataService = context.get('extra_data_service')

    try:
        minion = await minion_service.get(
            query={'minion_id': message.minion_id, 'master': message.master}, projection_model=EmptyModel
        )
        minion_id = minion.id
    except ObjectNotFoundException:
        return None

    static_items: dict[str, list[Any]] = {}
    updated_categories: list[str] = []
    updated_at = utc_now()

    for category_data in message.data_list:
        updated_categories.append(category_data.category_name)

        if category_data.category_type == MinionExtraDataType.STATIC:
            static_items.setdefault(f'extra_static.{message.sender}.{category_data.category_name}', []).extend(
                [
                    {**value.category_data, **value.minion_data, 'updated_at': updated_at}
                    for value in category_data.items
                ]
            )
        elif category_data.category_type == MinionExtraDataType.AGGREGATED:
            # TODO (i.moshkov): Remove old category extra data for this minion!!!

            # TODO (i.moshkov): May use bulk ops?
            for extra_data_item in category_data.items:
                await extra_data_service.update_or_create(
                    query={
                        'source': message.sender,
                        'name': category_data.category_name,
                        'data': extra_data_item.category_data,
                    },
                    data={f'minions.{minion_id!s}': {**extra_data_item.minion_data, 'updated_at': updated_at}},
                )

    try:
        if static_items:
            await minion_service.update(query=minion_id, data=static_items)
    except ObjectNotFoundException:
        return None

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
