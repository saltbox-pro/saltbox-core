import csv
from datetime import UTC, datetime
from typing import Annotated, Any, overload

from anyio import Path
from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.minion import MinionRepository, get_minion_repository
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
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel


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

    async def get_ids_by_query(self, query: dict[str, Any]) -> list[MinionIDs]:
        return await self.repo.get_list(query, skip=0, limit=0, projection_model=MinionIDs)

    async def get_unique_grain_values_by_field(
        self, field: str, query: dict[str, Any], skip: int = 0, limit: int | None = None
    ) -> UniqueGrainValuesResponse:
        query = self.repo.__prepare_query__(query)
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

        keys = [key for key in minion_keys.keys() if key != 'grains'] + [f'grains.{key}' for key in all_grains_keys]

        async with await Path(file_path).open(mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            await writer.writeheader()
            for item in data:
                row = item.model_dump(exclude={'grains', 'last_activity_seconds'})
                grains_dict = item.grains.model_dump() if hasattr(item.grains, 'model_dump') else dict(item.grains)
                for key in all_grains_keys:
                    row[f'grains.{key}'] = grains_dict.get(key)
                await writer.writerow(row)

        return file_path


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)


MinionServiceDependency = Annotated[MinionService, Depends(get_minion_service)]
