from typing import Annotated

from fastapi import Depends

from salt_box_core.config import SETTINGS, logger
from salt_box_core.db.exceptions import DuplicateKeyError, ObjectNotFoundError
from salt_box_core.db.mongo.schemas_base import PaginatedResponse, PyObjectId
from salt_box_core.schema_sync.repository import JSONSchemaRepository, get_json_schema_repository
from salt_box_core.schema_sync.schemas import JSONSchemaCreateSchema, JSONSchemaModel, JSONSchemaShortSchema
from salt_box_core.schema_sync.services.schema_sync_service import SchemaGitRepoService


class JSONSchemaService:
    def __init__(self, repo: JSONSchemaRepository) -> None:
        self.repo = repo

    async def get(self, id: PyObjectId) -> JSONSchemaModel:
        document = await self.repo.get({'_id': id})
        if not document:
            msg = 'JSON schema not found'
            raise ObjectNotFoundError(msg)
        return document

    async def get_list_paginated(
        self, query: None = None, limit: int = 0, skip: int = 0
    ) -> PaginatedResponse[JSONSchemaShortSchema]:
        total = await self.repo.count(query)
        docs = await self.repo.get_list(query, limit=limit, skip=skip, projection_model=JSONSchemaShortSchema)
        return PaginatedResponse[JSONSchemaShortSchema](total=total, data=docs)

    async def sync(self) -> dict:
        git_repo = SchemaGitRepoService(SETTINGS.salt_func_repo_url)
        git_repo.clone_or_pull()
        schemas = await git_repo.parse_schemas()
        parsed_schema_names = [schema['name'] for schema in schemas]
        removed_count = await self.repo.delete_many({'name': {'$nin': parsed_schema_names}})

        schema_docs = [JSONSchemaCreateSchema(**schema) for schema in schemas]

        created = []
        updated = []
        for schema in schema_docs:
            try:
                exist_doc = await self.repo.get({'name': schema.name}, projection_model=JSONSchemaShortSchema)
            except ObjectNotFoundError:
                exist_doc = None

            if not exist_doc:
                logger.debug('Try create: %s', schema)
                try:
                    await self.repo.create(schema)
                except DuplicateKeyError:
                    msg = f'JSON schema with name {schema.name} already exists'
                    logger.debug(msg)
                    raise DuplicateKeyError(msg) from None

                created.append(schema.name)
            elif exist_doc.commit_hash != schema.commit_hash:
                logger.debug('Try update: %s', schema.name)
                await self.repo.update({'name': schema.name}, schema)
                updated.append(schema.name)

        return {'created': created, 'updated': updated, 'removed_count': removed_count}


def get_json_schema_service(
    repo: Annotated[JSONSchemaRepository, Depends(get_json_schema_repository)],
) -> JSONSchemaService:
    return JSONSchemaService(repo)
