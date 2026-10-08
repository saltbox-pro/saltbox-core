from typing import Any

from faststream import Logger
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import ContextRepo, RabbitMessage

from saltbox_core.minion_collections.services.extra_data import ExtraDataService
from saltbox_core.minion_collections.services.extra_data_category import ExtraDataCategoryService
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import EmptyModel
from saltbox_sdk.event_bus.schemas import (
    MinionAddOrUpdateExtraDataRequestMessage,
    MinionExtraCategoriesSyncMessage,
    MinionRemoveExtraDataRequestMessage,
)
from saltbox_sdk.exceptions import ObjectNotFoundException

router = RabbitRouter(prefix='minions_')


@router.subscriber('extra_categories_sync')
async def extra_categories_sync(
    message: MinionExtraCategoriesSyncMessage, msg: RabbitMessage, context: ContextRepo, logger: Logger
) -> None:
    if message.target != 'core':
        return None

    extra_data_category_service: ExtraDataCategoryService = context.get('extra_data_category_service')

    for category in message.categories:
        await extra_data_category_service.update_or_create(
            query={'source': category.source, 'name': category.name},
            data={
                'type': category.type,
                'extra_fields_policy': category.extra_fields_policy,
                'fields': [field.model_dump() for field in category.fields],
                'is_system': True,
                'is_manual_data_allowed': bool(category.is_manual_data_allowed),
                'title': category.title,
                'description': category.description,
                'icon': category.icon,
                'is_single_item': category.is_single_item,
            },
        )

    return None


@router.subscriber('add_extra_data')
async def add_extra_data(
    message: MinionAddOrUpdateExtraDataRequestMessage, msg: RabbitMessage, context: ContextRepo, logger: Logger
) -> None:
    if message.target != 'core':
        return None

    await msg.ack()

    minion_service: MinionService = context.get('minion_service')
    extra_data_category_service: ExtraDataCategoryService = context.get('extra_data_category_service')
    extra_data_service: ExtraDataService = context.get('extra_data_service')

    try:
        minion = await minion_service.get(
            query={'minion_id': message.minion_id, 'master': message.master}, projection_model=EmptyModel
        )
    except ObjectNotFoundException:
        return None

    items_by_category: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for extra_data in message.data_list:
        category_key = (extra_data.category_source, extra_data.category_name)
        items_by_category.setdefault(category_key, []).extend(extra_data.items)

    for (source, name), items in items_by_category.items():
        category = await extra_data_category_service.get(query={'source': source, 'name': name})
        await extra_data_service.replace_items(category, [minion.id], items, is_system=True)

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
