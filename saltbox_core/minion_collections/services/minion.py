from collections.abc import AsyncIterator
from typing import Annotated, Any, get_args, get_origin, overload

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

from saltbox_core.minion_collections.exceptions import (
    MinionHasBeenActiveException,
    MinionMergeConflictException,
    MinionMergeIntoItselfException,
)
from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.collection import CollectionModel
from saltbox_core.minion_collections.schemas.filter import UniqueValuesResponse
from saltbox_core.minion_collections.schemas.minion import (
    GrainsSchema,
    MinionCreateSchema,
    MinionExportSchema,
    MinionMergeConflictStrategy,
    MinionMergeExtraDataStrategy,
    MinionModel,
    MinionTgtOnlySchema,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.utils.activity_filter import get_never_active_query
from saltbox_core.minion_collections.utils.unique_values import UniqueValueKind
from saltbox_sdk.db.mongo.schemas_base import EmptyModel, PyObjectId, SortOrder
from saltbox_sdk.exceptions import DuplicateKeyException, ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel
from saltbox_sdk.utilities.helpers import utc_now

JOINED_LIST_GRAINS = ['pythonversion', 'saltversioninfo']


def _get_grain_unique_value_kind(grain: str) -> UniqueValueKind:
    if grain in JOINED_LIST_GRAINS:
        return UniqueValueKind.JOINED_LIST

    field = next(
        (field for name, field in GrainsSchema.model_fields.items() if grain in (name, field.alias)),
        None,
    )
    if field is None:
        return UniqueValueKind.VALUE

    for field_type in get_args(field.annotation) or (field.annotation,):
        if field_type is list or get_origin(field_type) is list:
            return UniqueValueKind.LIST_ITEMS
        if field_type is dict or get_origin(field_type) is dict:
            return UniqueValueKind.DICT_KEYS

    return UniqueValueKind.VALUE


def _get_static_manual_categories(extra_static: dict[str, dict[str, list[dict[str, Any]]]]) -> set[tuple[str, str]]:
    categories: set[tuple[str, str]] = set()
    for source, items_by_name in extra_static.items():
        for name, items in items_by_name.items():
            for item in items:
                if not item.get('is_system'):
                    categories.add((source, name))

    return categories


class MinionService(MongoBaseService[MinionRepository, MinionModel, MinionCreateSchema, MinionUpdateSchema]):
    async def delete_by_ids(
        self,
        minion_ids: list[PyObjectId],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> int:
        from saltbox_core.salt.tiq_tasks import delete_minion_salt_keys_task

        minions = await self.get_list(
            {'_id': {'$in': minion_ids}}, session=session, projection_model=MinionTgtOnlySchema
        )
        deleted_count = await self.repo.delete_many({'_id': {'$in': minion_ids}}, session=session)
        await self.repo.extra_data_repository.pull_all_minions_entries(minion_ids, session=session)

        for minion in minions:
            await delete_minion_salt_keys_task.kiq(minion_id=minion.minion_id, master_id=minion.master)  # type: ignore

        return deleted_count

    async def update_never_active(
        self, minion_id: PyObjectId, collection: CollectionModel, data: dict[str, Any]
    ) -> None:
        queries: list[dict[str, Any]] = [{'_id': minion_id}, get_never_active_query()]
        if collection.full_query:
            queries.append(collection.full_query)

        try:
            await self.update(query={'$and': queries}, data=data)
        except ObjectNotFoundException:
            await self.get_in_collection(minion_id, collection, projection_model=EmptyModel)
            raise MinionHasBeenActiveException() from None
        except MongoDuplicateKeyError as e:
            if e.details and 'keyValue' in e.details:
                raise DuplicateKeyException(key_value=e.details['keyValue']) from None
            raise DuplicateKeyException(str(e)) from None

    async def merge(  # noqa: C901
        self,
        source_id: PyObjectId,
        target_id: PyObjectId,
        collection: CollectionModel,
        *,
        extra_data_strategy: MinionMergeExtraDataStrategy,
        conflict_strategy: MinionMergeConflictStrategy,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        if source_id == target_id:
            raise MinionMergeIntoItselfException()

        await self.get_in_collection(target_id, collection, projection_model=EmptyModel)
        await self.get_in_collection(source_id, collection, projection_model=EmptyModel)
        if not await self.repo.count({'$and': [{'_id': source_id}, get_never_active_query()]}, session=session):
            raise MinionHasBeenActiveException()

        extra_data_repo = self.repo.extra_data_repository

        if extra_data_strategy != MinionMergeExtraDataStrategy.USE_TARGET:
            source_static = await self.repo.get_static_extra_data(source_id, session=session)
            target_static = await self.repo.get_static_extra_data(target_id, session=session)
            target_manual = await extra_data_repo.get_minion_categories(target_id, is_system=False, session=session)
            target_manual |= _get_static_manual_categories(target_static)

            replaced: set[tuple[str, str]] = set()
            dropped: set[tuple[str, str]] = set()

            if extra_data_strategy == MinionMergeExtraDataStrategy.USE_SOURCE:
                replaced = target_manual
            else:
                source_manual = await extra_data_repo.get_minion_categories(source_id, is_system=False, session=session)
                source_manual |= _get_static_manual_categories(source_static)

                single_item_categories: set[tuple[str, str]] = set()
                for category in await extra_data_repo.extra_data_category_repository.get_list(
                    {'is_single_item': True}, session=session
                ):
                    single_item_categories.add((category.source, category.name))

                conflicts = single_item_categories & source_manual & target_manual
                if conflicts and conflict_strategy == MinionMergeConflictStrategy.ERROR:
                    raise MinionMergeConflictException([f'{source}.{name}' for source, name in sorted(conflicts)])
                if conflict_strategy == MinionMergeConflictStrategy.USE_SOURCE:
                    replaced = conflicts
                elif conflict_strategy == MinionMergeConflictStrategy.USE_TARGET:
                    dropped = conflicts

            items_by_category: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for source, items_by_name in target_static.items():
                for name, items in items_by_name.items():
                    if (source, name) in replaced:
                        items_by_category[(source, name)] = [item for item in items if item.get('is_system')]

            for source, items_by_name in source_static.items():
                for name, items in items_by_name.items():
                    if (source, name) in dropped:
                        continue
                    if (source, name) not in items_by_category:
                        items_by_category[(source, name)] = list(target_static.get(source, {}).get(name) or [])
                    items_by_category[(source, name)].extend(items)

            if items_by_category:
                await self.repo.set_static_extra_data_items(target_id, items_by_category, session=session)

            for source, name in sorted(replaced):
                await extra_data_repo.pull_minions_entries(source, name, [target_id], is_system=False, session=session)

            await extra_data_repo.move_minion_entries(
                source_id, target_id, excluded_categories=sorted(dropped), session=session
            )

        await self.repo.delete_many({'_id': source_id}, session=session)
        await extra_data_repo.pull_all_minions_entries([source_id], session=session)

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

    async def get_unique_grain_values(
        self, field: str, query: dict[str, Any], skip: int = 0, limit: int | None = None
    ) -> UniqueValuesResponse:
        if not field.startswith('grains.'):
            return UniqueValuesResponse(total=0, data=[])

        grain = field.removeprefix('grains.')
        total, data = await self.repo.get_unique_grain_values(
            query=await self.repo.__prepare_query__(query),
            grain=grain,
            kind=_get_grain_unique_value_kind(grain),
            skip=skip,
            limit=limit or 0,
        )

        return UniqueValuesResponse.model_validate({'total': total, 'data': data})

    async def get_targeting_masters(
        self, query: dict[str, Any], sort: dict[str, SortOrder] | None = None
    ) -> list[dict[str, Any]]:
        return await self.repo.get_targeting_masters(query=await self.repo.__prepare_query__(query), sort=sort)

    async def process_presence(self, master_id: str, minions: list[str]) -> None:
        await self.bulk_update(
            query={'master': master_id, 'minion_id': {'$in': minions}},
            data={'last_activity': utc_now()},
        )

    async def process_grains(self, master_id: str, minion_id: str, grains: dict[str, Any]) -> None:
        try:
            await self.update(
                query={'master': master_id, 'minion_id': minion_id},
                data={
                    'grains': GrainsSchema.model_validate(grains).model_dump(by_alias=True),
                    'last_activity': utc_now(),
                },
            )
        except ObjectNotFoundException:
            minion_obj = {
                'minion_id': minion_id,
                'master': master_id,
                'grains': grains,
                'last_activity': utc_now(),
            }
            await self.create(data=MinionCreateSchema.model_validate(minion_obj).model_dump(by_alias=True))

    async def get_export_columns(self, query: dict[str, Any] | None) -> list[str]:
        grains_keys = await self.repo.get_grains_keys(query)

        return [name for name in MinionExportSchema.model_fields if name != 'grains'] + [
            f'grains.{key}' for key in grains_keys
        ]

    async def iter_export_rows(
        self,
        query: dict[str, Any] | None,
        skip: int = 0,
        limit: int = 0,
        sort: dict[str, SortOrder] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for minion in self.iter_list(query, limit, skip, sort=sort, projection_model=MinionExportSchema):
            row = minion.model_dump(exclude={'grains'})
            for key, value in minion.grains.model_dump(by_alias=True).items():
                row[f'grains.{key}'] = value

            yield row


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)


MinionServiceDependency = Annotated[MinionService, Depends(get_minion_service)]
