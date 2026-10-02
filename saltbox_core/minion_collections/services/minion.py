import csv
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, NoReturn, overload

from anyio import Path
from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.collection import CollectionModel
from saltbox_core.minion_collections.schemas.extra_data import (
    CollectionExtraDataListItemSchema,
    ExtraDataListItemSchema,
)
from saltbox_core.minion_collections.schemas.filter import UniqueGrainValuesResponse
from saltbox_core.minion_collections.schemas.minion import (
    GrainsSchema,
    MinionCreateSchema,
    MinionIDs,
    MinionModel,
    MinionTgtOnlySchema,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.services.pipeline_builder import MongoPipelineBuilder
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.db.schemas_base import PaginatedResponse
from saltbox_sdk.event_bus.schemas import ExtraDataCategoryType
from saltbox_sdk.exceptions import ObjectNotFoundException, PermissionDeniedException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel
from saltbox_sdk.utilities.helpers import utc_now


class MinionService(MongoBaseService[MinionRepository, MinionModel, MinionCreateSchema, MinionUpdateSchema]):
    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> int:
        from saltbox_core.salt.tiq_tasks import delete_minion_salt_keys_task

        minion = await self.get(query=query, session=session, projection_model=MinionTgtOnlySchema)
        await delete_minion_salt_keys_task.kiq(minion_id=minion.minion_id, master_id=minion.master)  # type: ignore
        deleted_count = await super().delete(query=query, session=session)

        return deleted_count

    @overload
    async def get_by_master_and_id(self, master: str, minion_id: str) -> MinionModel: ...

    @overload
    async def get_by_master_and_id(
        self, master: str, minion_id: str, *, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get_by_master_and_id(
        self, master: str, minion_id: str, *, projection_model: type[ProjectionModel] | None = None
    ) -> MinionModel | ProjectionModel:
        query = {'master': master, 'minion_id': minion_id}

        if projection_model:
            return await self.get(query=query, projection_model=projection_model)
        else:
            return await self.get(query=query)

    async def get_in_collection(
        self, minion_id: PyObjectId, collection: CollectionModel | None, *, projection_model: type[ProjectionModel]
    ) -> ProjectionModel:
        query: dict[str, Any] = {'_id': minion_id}
        if collection is not None and collection.full_query:
            query = {'$and': [query, collection.full_query]}

        return await self.get(query=query, projection_model=projection_model)

    async def get_ids_by_query(self, query: dict[str, Any]) -> list[MinionIDs]:
        return await self.repo.get_list(query, skip=0, limit=0, projection_model=MinionIDs)

    async def get_unique_grain_values_by_field(
        self, field: str, query: dict[str, Any], skip: int = 0, limit: int | None = None
    ) -> UniqueGrainValuesResponse:
        query = await self.repo.__prepare_query__(query)
        pipeline_builder = MongoPipelineBuilder(field, query, skip, limit)
        pipeline = pipeline_builder.build()
        full_pipeline = [stage for stage in pipeline if '$skip' not in stage and '$limit' not in stage]
        logger.debug('pipeline: %s', pipeline)
        data = await self.repo.aggregate(pipeline)
        full_data = await self.repo.aggregate(full_pipeline)
        return UniqueGrainValuesResponse(total=len(full_data), data=data)

    async def process_presence(self, master_id: str, minions: list[str], stamp: float) -> None:
        await self.bulk_update(
            query={'master': master_id, 'minion_id': {'$in': minions}},
            data={'last_activity': datetime.fromtimestamp(stamp, tz=UTC)},
        )

    async def process_grains(self, master_id: str, minion_id: str, grains: dict[str, Any]) -> None:
        try:
            await self.update(
                query={'master': master_id, 'minion_id': minion_id},
                data={'grains': GrainsSchema.model_validate(grains).model_dump(by_alias=True)},
            )
        except ObjectNotFoundException:
            minion_obj = {
                'minion_id': minion_id,
                'master': master_id,
                'grains': grains,
            }
            await self.create(data=MinionCreateSchema.model_validate(minion_obj).model_dump(by_alias=True))

    async def export_to_csv(self, query: dict[str, Any], skip: int = 0, limit: int = 0) -> str:
        data = await self.get_list(query, skip=skip, limit=limit)

        await Path('./reports').mkdir(parents=True, exist_ok=True)
        current_datetime = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        file_path = f'./reports/minions_{current_datetime}.csv'

        minion_keys = MinionModel.model_fields

        # Get all unique grains keys via pipeline
        grains_pipeline: list[dict] = [
            {'$project': {'grains': 1}},
            {'$replaceRoot': {'newRoot': '$grains'}},
            {'$project': {'keys': {'$objectToArray': '$$ROOT'}}},
            {'$unwind': '$keys'},
            {'$group': {'_id': None, 'all_keys': {'$addToSet': '$keys.k'}}},
        ]
        grains_keys_result = await self.repo.aggregate(grains_pipeline)
        if grains_keys_result and grains_keys_result[0].get('all_keys'):
            all_grains_keys = grains_keys_result[0]['all_keys']
            logger.debug('Grains + custom: %s', all_grains_keys)
        else:
            # fallback: only standard
            all_grains_keys = list(getattr(GrainsSchema, 'model_fields', {}).keys())
            logger.debug('Grains (standard only): %s', all_grains_keys)

        keys = [key for key in minion_keys.keys() if key not in {'grains', 'extra'}] + [
            f'grains.{key}' for key in all_grains_keys
        ]

        async with await Path(file_path).open(mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            await writer.writeheader()
            for item in data:
                row = item.model_dump(exclude={'grains', 'last_activity_seconds', 'extra'})
                grains_dict = item.grains.model_dump() if hasattr(item.grains, 'model_dump') else dict(item.grains)
                for key in all_grains_keys:
                    row[f'grains.{key}'] = grains_dict.get(key)
                await writer.writerow(row)

        return file_path

    async def get_paginated_extra_data_list(
        self,
        *,
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        field_names: list[str] | None = None,
        search_str: str | None = None,
        escape_search_str: bool = True,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> PaginatedResponse[ExtraDataListItemSchema]:
        query = await self.repo.__prepare_query__(query)

        total, data = await self.repo.get_extra_data_list_paginated(
            query=query,
            category_source=category_source,
            category_name=category_name,
            category_type=category_type,
            field_names=field_names,
            search_str=search_str,
            escape_search_str=escape_search_str,
            limit=limit,
            skip=skip,
            sort=sort,
            session=session,
        )

        return PaginatedResponse[ExtraDataListItemSchema](total=total, data=data)

    async def get_paginated_grouped_extra_data_list(
        self,
        *,
        group_by_fields: list[str],
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        search_str: str | None = None,
        escape_search_str: bool = True,
        limit: int = 0,
        skip: int = 0,
        sort: dict[str, SortOrder] | None = None,
        session: MongoAsyncClientSession | None = None,
    ) -> PaginatedResponse[CollectionExtraDataListItemSchema]:
        query = await self.repo.__prepare_query__(query)

        if category_type == ExtraDataCategoryType.AGGREGATED:
            minion_ids = await self.repo.get_ids(query, session=session)

            total, data = await self.repo.extra_data_repository.get_grouped_paginated(
                minion_ids=minion_ids,
                category_source=category_source,
                category_name=category_name,
                group_by_fields=group_by_fields,
                search_str=search_str,
                escape_search_str=escape_search_str,
                limit=limit,
                skip=skip,
                sort=sort,
                session=session,
            )

            return PaginatedResponse[CollectionExtraDataListItemSchema](total=total, data=data)

        total, data = await self.repo.get_extra_data_list_paginated(
            query=query,
            category_source=category_source,
            category_name=category_name,
            category_type=category_type,
            group_by_fields=group_by_fields,
            search_str=search_str,
            escape_search_str=escape_search_str,
            limit=limit,
            skip=skip,
            sort=sort,
            session=session,
        )

        return PaginatedResponse[CollectionExtraDataListItemSchema](total=total, data=data)

    async def iter_extra_data_list(
        self,
        *,
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        field_names: list[str] | None = None,
        search_str: str | None = None,
        escape_search_str: bool = True,
        sort: dict[str, SortOrder] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        query = await self.repo.__prepare_query__(query)

        async for row in self.repo.iter_extra_data(
            query=query,
            category_source=category_source,
            category_name=category_name,
            category_type=category_type,
            field_names=field_names,
            search_str=search_str,
            escape_search_str=escape_search_str,
            sort=sort,
        ):
            yield row

    async def iter_grouped_extra_data_list(
        self,
        *,
        group_by_fields: list[str],
        query: dict[str, Any] | None = None,
        category_source: str,
        category_name: str,
        category_type: ExtraDataCategoryType,
        search_str: str | None = None,
        escape_search_str: bool = True,
        sort: dict[str, SortOrder] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        query = await self.repo.__prepare_query__(query)

        if category_type == ExtraDataCategoryType.AGGREGATED:
            rows = self.repo.extra_data_repository.iter_grouped(
                minion_ids=await self.repo.get_ids(query),
                category_source=category_source,
                category_name=category_name,
                group_by_fields=group_by_fields,
                search_str=search_str,
                escape_search_str=escape_search_str,
                sort=sort,
            )
        else:
            rows = self.repo.iter_extra_data(
                query=query,
                category_source=category_source,
                category_name=category_name,
                category_type=category_type,
                group_by_fields=group_by_fields,
                search_str=search_str,
                escape_search_str=escape_search_str,
                sort=sort,
            )

        async for row in rows:
            yield row

    @staticmethod
    def _new_static_extra_data_item(data: dict[str, Any], *, is_system: bool, updated_at: datetime) -> dict[str, Any]:
        return {'_id': PyObjectId(), 'is_system': is_system, 'updated_at': updated_at, 'data': data}

    async def _raise_for_unchanged_static_extra_data_item(
        self, minion_id: PyObjectId, source: str, name: str, item_id: PyObjectId
    ) -> NoReturn:
        if await self.repo.get_static_extra_data_item(minion_id, source, name, item_id) is None:
            raise ObjectNotFoundException(obj_type='extra_static_item', query={'_id': item_id})

        msg = 'Extra data items collected automatically cannot be changed manually.'
        raise PermissionDeniedException(msg)

    async def add_static_extra_data_items(
        self, minion_ids: list[PyObjectId], source: str, name: str, data: dict[str, Any], *, replace_manual: bool
    ) -> list[dict[str, Any]]:
        existing_minion_ids = await self.repo.get_ids({'_id': {'$in': minion_ids}})
        if not existing_minion_ids:
            return []

        updated_at = utc_now()
        items_by_minion = {
            minion_id: self._new_static_extra_data_item(data, is_system=False, updated_at=updated_at)
            for minion_id in existing_minion_ids
        }
        await self.repo.add_static_extra_data_items(source, name, items_by_minion, replace_manual=replace_manual)

        return [{'minion_id': minion_id, **item} for minion_id, item in items_by_minion.items()]

    async def update_static_extra_data_item(
        self, minion_id: PyObjectId, source: str, name: str, item_id: PyObjectId, data: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self.repo.set_manual_static_extra_data_item_data(minion_id, source, name, item_id, data)
        if result.matched_count == 0:
            await self._raise_for_unchanged_static_extra_data_item(minion_id, source, name, item_id)

        item = await self.repo.get_static_extra_data_item(minion_id, source, name, item_id)
        if item is None:
            raise ObjectNotFoundException(obj_type='extra_static_item', query={'_id': item_id})

        return item

    async def delete_static_extra_data_item(
        self, minion_id: PyObjectId, source: str, name: str, item_id: PyObjectId
    ) -> None:
        result = await self.repo.pull_manual_static_extra_data_item(minion_id, source, name, item_id)
        if result.matched_count == 0:
            await self._raise_for_unchanged_static_extra_data_item(minion_id, source, name, item_id)

    async def remove_static_category_data(self, source: str, name: str) -> None:
        await self.repo.unset_static_category_field(source, name)

    async def replace_system_static_extra_data(
        self, minion_id: PyObjectId, data_by_category: dict[tuple[str, str], list[dict[str, Any]]], updated_at: datetime
    ) -> None:
        items_by_category = {
            category: [self._new_static_extra_data_item(data, is_system=True, updated_at=updated_at) for data in datas]
            for category, datas in data_by_category.items()
        }

        result = await self.repo.replace_system_static_extra_data_items(minion_id, items_by_category)
        if result.matched_count == 0:
            raise ObjectNotFoundException(obj_type='minion', query={'_id': minion_id})


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)


MinionServiceDependency = Annotated[MinionService, Depends(get_minion_service)]
