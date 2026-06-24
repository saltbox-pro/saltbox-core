import json
from typing import Annotated, Any, ClassVar

import anyio
import pymongo
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import logger
from saltbox_core.jobs.schemas.job_sc_schemas import JobSchemaCreateSchema, JobSchemaModel, JobSchemaUpdateSchema
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.exceptions import ObjectNotFoundException


class JobSchemaRepository(BaseMongoRepository[JobSchemaModel]):
    _PATH_TO_SCHEMAS_DIR = anyio.Path(__file__).parent.joinpath('fixtures/schemas')

    class Meta:
        collection_name = 'job_schemas'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'name_unique_index_asc': [('name', pymongo.ASCENDING)]
        }

    async def parse_schemas(self) -> tuple[list[dict], list[str]]:
        schemas = []
        errors = []
        async for file in self._PATH_TO_SCHEMAS_DIR.rglob('*.json'):
            try:
                content = json.loads(await file.read_text())
                if not isinstance(content, dict):
                    msg = f'{file}: Schema is not a dictionary'
                    errors.append(msg)

                schema = {
                    'name': file.name.replace('.json', ''),
                    'json_schema': content.get('json_schema', {}),
                    'ui_schema': content.get('ui_schema', {}),
                }
                schemas.append(schema)
            except json.JSONDecodeError as e:
                msg = f'{file}: Failed to parse file ({e!s})'
                logger.error(msg)
                errors.append(msg)
        return schemas, errors

    async def sync_and_cleanup_schemas(
        self, schemas: list[dict[str, Any]], parsed_schema_names: list[str]
    ) -> tuple[list[str], list[str], int]:
        """Save schemas to the database, removing any that are not in the provided list."""
        removed_count = await self.delete_many({'name': {'$nin': parsed_schema_names}})
        created = []
        updated = []

        for schema in schemas:
            try:
                existing_schema = await self.get({'name': schema['name']})
            except ObjectNotFoundException:
                existing_schema = None

            if not existing_schema:
                logger.debug('Try create: %s', schema['name'])
                schema_create_obj = JobSchemaCreateSchema(**schema)
                await self.create(schema_create_obj)
                created.append(schema_create_obj.name)
            else:
                logger.debug('Try update: %s', schema['name'])
                schema_update_obj = JobSchemaUpdateSchema(**schema)
                await self.update(
                    {'name': schema['name']},
                    schema_update_obj,
                )
                updated.append(schema['name'])

        return created, updated, removed_count

    async def _post_create_collection(self) -> None:
        schemas, errors = await self.parse_schemas()
        parsed_schema_names = [schema['name'] for schema in schemas]
        created, updated, removed_count = await self.sync_and_cleanup_schemas(schemas, parsed_schema_names)

        logger.info(
            'Job schemas sync completed. Created: %s, Updated: %s, Removed: %s, Errors: %s',
            created,
            updated,
            removed_count,
            errors,
        )


def get_job_schema_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> JobSchemaRepository:
    return JobSchemaRepository(db)
