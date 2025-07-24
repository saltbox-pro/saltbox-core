import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, overload

from fastapi import Depends

from saltbox_core.config import logger
from saltbox_core.minion_collections.repositories.minion_repository import MinionRepository, get_minion_repository
from saltbox_core.minion_collections.schemas.filter_schemas import UniqueGrainValuesResponse
from saltbox_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionIDs,
    MinionModel,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.services.pipeline_builder import MongoPipelineBuilder
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService, ProjectionModel


class MinionService(MongoBaseService[MinionRepository, MinionModel, MinionCreateSchema, MinionUpdateSchema]):
    @overload
    async def get_by_master_and_id(self, master: str, minion_id: str) -> MinionModel: ...

    @overload
    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel]
    ) -> ProjectionModel: ...

    async def get_by_master_and_id(
        self, master: str, minion_id: str, projection_model: type[ProjectionModel] | None = None
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

    async def export_to_csv(self, query: dict[str, Any], skip: int = 0, limit: int = 0) -> str:
        data = await self.get_list(query, skip=skip, limit=limit)
        if not data:
            return ''

        Path('./reports').mkdir(parents=True, exist_ok=True)
        current_datetime = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
        file_path = f'./reports/minions_{current_datetime}.csv'

        minion_keys = MinionModel.model_fields
        grains_keys = GrainsSchema.model_fields

        keys = [key for key in minion_keys.keys() if key != 'grains'] + [f'grains.{key}' for key in grains_keys.keys()]

        with Path(file_path).open(mode='w', newline='') as file:  # noqa: ASYNC230
            writer = csv.DictWriter(file, fieldnames=keys)
            writer.writeheader()
            for item in data:
                row = item.model_dump(exclude={'grains', 'last_activity_seconds'})
                row.update({f'grains.{key}': item.grains.model_dump()[key] for key in grains_keys.keys()})
                writer.writerow(row)

        return file_path


def get_minion_service(
    repo: Annotated[MinionRepository, Depends(get_minion_repository)],
) -> MinionService:
    return MinionService(repo)
