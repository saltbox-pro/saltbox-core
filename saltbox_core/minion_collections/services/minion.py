from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, get_args, get_origin, overload

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.collection import CollectionModel
from saltbox_core.minion_collections.schemas.filter import UniqueValuesResponse
from saltbox_core.minion_collections.schemas.minion import (
    GrainsSchema,
    MinionCreateSchema,
    MinionExportSchema,
    MinionModel,
    MinionTgtOnlySchema,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.utils.unique_values import UniqueValueKind
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel

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
