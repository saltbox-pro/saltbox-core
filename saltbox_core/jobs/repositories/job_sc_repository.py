import json
from typing import Annotated, Any, ClassVar, cast

import anyio
import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema, JobSchemaModel
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class JobSchemaRepository(BaseMongoRepository[JobSchemaModel]):
    _PATH_TO_DEFAULT_SCHEMA = anyio.Path(__file__).parent.joinpath('fixtures/default_func_schema.json')
    _PATH_TO_DEFAULT_UI_SCHEMA = anyio.Path(__file__).parent.joinpath('fixtures/default_func_ui_schema.json')

    class Meta:
        collection_name = 'job_schemas'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_unique_index_asc': [('name', pymongo.ASCENDING)]
        }

    async def _post_create_collection(self) -> None:
        is_default_schema_exists = await self.exists(query={'name': 'default'})
        if not is_default_schema_exists:
            logger.debug('Creating default schema')

            default_schema = await self._load_default_schema(self._PATH_TO_DEFAULT_SCHEMA)
            default_ui_schema = await self._load_default_schema(self._PATH_TO_DEFAULT_UI_SCHEMA)

            created_schema_id = await self.create(
                data=JobSchemaCreateSchema.model_validate(
                    obj={
                        'name': 'default',
                        'json_schema': default_schema,
                        'ui_schema': default_ui_schema,
                        'commit_hash': '',
                    }
                )
            )
            created_schema: JobSchemaModel = await self.get(query=created_schema_id)
            logger.info('Created default schema: %s', created_schema)
        else:
            logger.debug('Default schema already exists')

    async def _load_default_schema(self, path: anyio.Path) -> dict[str, Any]:
        async with await path.open('r') as f:
            return cast(dict[str, Any], json.loads(await f.read()))


def get_job_schema_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobSchemaRepository:
    return JobSchemaRepository(db)
