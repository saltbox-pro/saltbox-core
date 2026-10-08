from collections.abc import AsyncIterator
from typing import Annotated, Any, NoReturn

from fastapi import Depends

from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository, get_extra_data_repository
from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.extra_data import (
    CollectionExtraDataListItemSchema,
    ExtraDataCreateSchema,
    ExtraDataListItemSchema,
    ExtraDataModel,
    ExtraDataUpdateSchema,
)
from saltbox_core.minion_collections.schemas.extra_data_category import ExtraDataCategoryModel
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType, MinionExtraDataExtraFieldsPolicy
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException, SaltBoxValidationException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.utilities.helpers import utc_now


class ExtraDataService(
    MongoBaseService[
        ExtraDataRepository,
        ExtraDataModel,
        ExtraDataCreateSchema,
        ExtraDataUpdateSchema,
    ]
):
    def __init__(self, repo: ExtraDataRepository, minion_repo: MinionRepository) -> None:
        super().__init__(repo)
        self.minion_repo = minion_repo

    # Write

    @staticmethod
    def _clean_datas(
        category: ExtraDataCategoryModel,
        minion_ids: list[PyObjectId],
        datas: list[dict[str, Any]],
        *,
        is_system: bool,
        is_minion_data_only: bool = False,
    ) -> list[dict[str, Any]]:
        field_names = [field.name for field in category.fields]
        cleaned_datas: list[dict[str, Any]] = []

        for data in datas:
            if is_system and category.extra_fields_policy == MinionExtraDataExtraFieldsPolicy.IGNORE:
                data = {key: value for key, value in data.items() if key in field_names}

            if not data:
                if is_system:
                    continue
                msg = 'Extra data item must contain at least one field.'
                raise SaltBoxValidationException(msg)

            try:
                cleaned_datas.append(category.clean_data(data, is_minion_data_only=is_minion_data_only))
            except SaltBoxValidationException as error:
                if not is_system:
                    raise
                logger.warning(
                    f'Skipped extra data item of category `{category.source}.{category.name}` '
                    f'for minions {minion_ids}: {error}'
                )

        if category.is_single_item and len(cleaned_datas) > 1:
            msg = f'Category `{category.source}.{category.name}` allows only one item per minion.'
            if not is_system:
                raise SaltBoxValidationException(msg)
            logger.warning(f'{msg} Got {len(cleaned_datas)} items for minions {minion_ids}, the last one is kept.')
            cleaned_datas = cleaned_datas[-1:]

        return cleaned_datas

    async def _write_items(
        self,
        category: ExtraDataCategoryModel,
        minion_ids: list[PyObjectId],
        datas: list[dict[str, Any]],
        *,
        is_system: bool,
        replace: bool,
    ) -> list[dict[str, Any]]:
        existing_minion_ids = await self.minion_repo.get_ids({'_id': {'$in': minion_ids}})
        if not existing_minion_ids or (not datas and not replace):
            return []

        updated_at = utc_now()
        items: list[dict[str, Any]] = []

        if category.type == ExtraDataCategoryType.STATIC:
            items_by_minion: dict[PyObjectId, list[dict[str, Any]]] = {}
            for minion_id in existing_minion_ids:
                minion_items: list[dict[str, Any]] = []
                for data in datas:
                    item = {'_id': PyObjectId(), 'is_system': is_system, 'updated_at': updated_at, 'data': data}
                    minion_items.append(item)
                    items.append({'minion_id': minion_id, **item})
                items_by_minion[minion_id] = minion_items

            if replace:
                await self.minion_repo.replace_static_extra_data_items(
                    category.source, category.name, items_by_minion, is_system=is_system
                )
            else:
                await self.minion_repo.push_static_extra_data_items(category.source, category.name, items_by_minion)

            return items

        if replace:
            await self.repo.pull_minions_entries(
                category.source, category.name, existing_minion_ids, is_system=is_system
            )

        for data in datas:
            category_data, minion_data = category.split_data(data)
            entries: list[dict[str, Any]] = []
            for minion_id in existing_minion_ids:
                entry = {
                    '_id': PyObjectId(),
                    'minion_id': minion_id,
                    'is_system': is_system,
                    'updated_at': updated_at,
                    'data': minion_data,
                }
                entries.append(entry)
                items.append({**entry, 'data': {**category_data, **minion_data}})

            await self.repo.push_minions_entries(category.source, category.name, category_data, entries)

        return items

    async def add_items(
        self,
        category: ExtraDataCategoryModel,
        minion_ids: list[PyObjectId],
        data: dict[str, Any],
        *,
        is_system: bool,
    ) -> list[dict[str, Any]]:
        if category.is_single_item:
            return await self.replace_items(category, minion_ids, [data], is_system=is_system)

        datas = self._clean_datas(category, minion_ids, [data], is_system=is_system)

        return await self._write_items(category, minion_ids, datas, is_system=is_system, replace=False)

    async def replace_items(
        self,
        category: ExtraDataCategoryModel,
        minion_ids: list[PyObjectId],
        datas: list[dict[str, Any]],
        *,
        is_system: bool,
    ) -> list[dict[str, Any]]:
        datas = self._clean_datas(category, minion_ids, datas, is_system=is_system)

        return await self._write_items(category, minion_ids, datas, is_system=is_system, replace=True)

    async def _get_item(
        self, category: ExtraDataCategoryModel, minion_id: PyObjectId, item_id: PyObjectId
    ) -> dict[str, Any] | None:
        if category.type == ExtraDataCategoryType.STATIC:
            item = await self.minion_repo.get_static_extra_data_item(minion_id, category.source, category.name, item_id)
            if item is None:
                return None
            return {'minion_id': minion_id, **item}

        return await self.repo.get_minion_entry(category.source, category.name, minion_id, item_id)

    async def _raise_for_unchanged_item(
        self, category: ExtraDataCategoryModel, minion_id: PyObjectId, item_id: PyObjectId
    ) -> NoReturn:
        if await self._get_item(category, minion_id, item_id) is None:
            raise ObjectNotFoundException(obj_type='extra_data_item', query={'_id': item_id})

        msg = 'Extra data items collected automatically cannot be changed manually.'
        raise PermissionDeniedException(msg)

    async def update_item(
        self, category: ExtraDataCategoryModel, minion_id: PyObjectId, item_id: PyObjectId, data: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._clean_datas(
            category,
            [minion_id],
            [data],
            is_system=False,
            is_minion_data_only=category.type == ExtraDataCategoryType.AGGREGATED,
        )[0]

        if category.type == ExtraDataCategoryType.STATIC:
            result = await self.minion_repo.set_manual_static_extra_data_item_data(
                minion_id, category.source, category.name, item_id, data
            )
        else:
            category_data, minion_data = category.split_data(data)
            if category_data:
                msg = f'Only minion fields can be changed in aggregated categories, got: {", ".join(category_data)}'
                raise SaltBoxValidationException(msg)

            result = await self.repo.set_manual_minion_entry_data(
                category.source, category.name, minion_id, item_id, minion_data
            )

        if result.matched_count == 0:
            await self._raise_for_unchanged_item(category, minion_id, item_id)

        item = await self._get_item(category, minion_id, item_id)
        if item is None:
            raise ObjectNotFoundException(obj_type='extra_data_item', query={'_id': item_id})

        return item

    async def delete_item(self, category: ExtraDataCategoryModel, minion_id: PyObjectId, item_id: PyObjectId) -> None:
        if category.type == ExtraDataCategoryType.STATIC:
            result = await self.minion_repo.pull_manual_static_extra_data_item(
                minion_id, category.source, category.name, item_id
            )
        else:
            result = await self.repo.pull_manual_minion_entry(category.source, category.name, minion_id, item_id)

        if result.matched_count == 0:
            await self._raise_for_unchanged_item(category, minion_id, item_id)

    async def remove_category_data(self, category: ExtraDataCategoryModel) -> None:
        if category.type == ExtraDataCategoryType.STATIC:
            await self.minion_repo.unset_static_category_field(category.source, category.name)
        else:
            await self.delete_many({'source': category.source, 'name': category.name})

    async def remove_category_field(self, category: ExtraDataCategoryModel, field_name: str) -> None:
        if category.type == ExtraDataCategoryType.STATIC:
            await self.minion_repo.remove_static_category_data_field(category.source, category.name, field_name)
        elif field_name in category.minion_fields:
            await self.repo.unset_minions_data_field(category.source, category.name, field_name)
        elif await self.count({'source': category.source, 'name': category.name}) > 0:
            msg = 'Category fields of aggregated categories can only be deleted while the category has no data.'
            raise SaltBoxValidationException(msg)

    # Read

    async def get_minion_items_paginated(
        self,
        category: ExtraDataCategoryModel,
        *,
        query: dict[str, Any],
        search_str: str | None = None,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
    ) -> PaginatedResponse[ExtraDataListItemSchema]:
        total, data = await self.minion_repo.get_extra_data_list_paginated(
            query=await self.minion_repo.__prepare_query__(query),
            category_source=category.source,
            category_name=category.name,
            category_type=category.type,
            field_names=[field.name for field in category.fields],
            search_str=search_str,
            limit=limit,
            skip=skip,
            sort=sort,
        )

        return PaginatedResponse[ExtraDataListItemSchema](total=total, data=data)

    async def iter_minion_items(
        self,
        category: ExtraDataCategoryModel,
        *,
        query: dict[str, Any],
        search_str: str | None = None,
        sort: dict[str, SortOrder] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        rows = self.minion_repo.iter_extra_data(
            query=await self.minion_repo.__prepare_query__(query),
            category_source=category.source,
            category_name=category.name,
            category_type=category.type,
            field_names=[field.name for field in category.fields],
            search_str=search_str,
            sort=sort,
        )

        async for row in rows:
            yield row

    async def get_grouped_items_paginated(
        self,
        category: ExtraDataCategoryModel,
        *,
        query: dict[str, Any],
        search_str: str | None = None,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
    ) -> PaginatedResponse[CollectionExtraDataListItemSchema]:
        query = await self.minion_repo.__prepare_query__(query)

        if category.type == ExtraDataCategoryType.AGGREGATED:
            total, data = await self.repo.get_grouped_paginated(
                minion_ids=await self.minion_repo.get_ids(query),
                category_source=category.source,
                category_name=category.name,
                group_by_fields=category.category_fields,
                search_str=search_str,
                limit=limit,
                skip=skip,
                sort=sort,
            )
        else:
            total, data = await self.minion_repo.get_extra_data_list_paginated(
                query=query,
                category_source=category.source,
                category_name=category.name,
                category_type=category.type,
                group_by_fields=category.category_fields,
                search_str=search_str,
                limit=limit,
                skip=skip,
                sort=sort,
            )

        return PaginatedResponse[CollectionExtraDataListItemSchema](total=total, data=data)

    async def iter_grouped_items(
        self,
        category: ExtraDataCategoryModel,
        *,
        query: dict[str, Any],
        search_str: str | None = None,
        sort: dict[str, SortOrder] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        query = await self.minion_repo.__prepare_query__(query)

        if category.type == ExtraDataCategoryType.AGGREGATED:
            rows = self.repo.iter_grouped(
                minion_ids=await self.minion_repo.get_ids(query),
                category_source=category.source,
                category_name=category.name,
                group_by_fields=category.category_fields,
                search_str=search_str,
                sort=sort,
            )
        else:
            rows = self.minion_repo.iter_extra_data(
                query=query,
                category_source=category.source,
                category_name=category.name,
                category_type=category.type,
                group_by_fields=category.category_fields,
                search_str=search_str,
                sort=sort,
            )

        async for row in rows:
            yield row


def get_extra_data_service(
    repo: Annotated[ExtraDataRepository, Depends(get_extra_data_repository)],
    minion_repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> ExtraDataService:
    return ExtraDataService(repo, minion_repo=minion_repo)
