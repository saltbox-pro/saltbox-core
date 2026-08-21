import json
from typing import Annotated, Any, TypeVar, overload, override

from fastapi import Depends
from pydantic import BaseModel
from pymongo.asynchronous.client_session import AsyncClientSession

from saltbox_core.config import SETTINGS, logger
from saltbox_core.pillars.repository import PillarRepository, get_pillar_repository
from saltbox_core.pillars.schemas import PillarTgtType
from saltbox_core.task_templates.exceptions import TaskTemplateNotFoundException
from saltbox_core.task_templates.repositories.template import TaskTemplateRepository, get_task_template_repository
from saltbox_core.task_templates.schemas.template import (
    TaskTemplateAggregatedModel,
    TaskTemplateCreateSchema,
    TaskTemplateDefaultsOnlySchema,
    TaskTemplateModel,
    TaskTemplatePublicWithContentSchema,
    TaskTemplateSchemasProjection,
    TaskTemplateUpdateSchema,
)
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException

# from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.utilities.json_schema import Draft4ValidatorWithDefaults

ProjectionModel = TypeVar('ProjectionModel', bound=BaseModel)


class TaskTemplateService(
    MongoBaseService[
        TaskTemplateRepository,
        TaskTemplateModel,
        TaskTemplateCreateSchema,
        TaskTemplateUpdateSchema,
    ]
):
    def __init__(self, repo: TaskTemplateRepository, pillar_repo: PillarRepository) -> None:
        super().__init__(repo)
        self._pillar_repo = pillar_repo

    @override
    async def delete(
        self,
        query: dict[str, Any] | PyObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            # Remove all related pillars
            tpl = await self.get(query=query, session=s, projection_model=TaskTemplateAggregatedModel)
            pillar_query = {
                'tgt_type': PillarTgtType.TASK_TPL,
                'pillarenv': {
                    '$regex': f'task_tpl:{tpl.id}.*',
                },
            }
            await self._pillar_repo.delete_many(query=pillar_query, session=s)

            result = await super().delete(query=query, session=s)
        await self._remove_files(tpl)

        return result

    async def _remove_files(self, tpl: TaskTemplateAggregatedModel) -> None:
        if tpl.sls_rel_path:
            serv_sls_file = SETTINGS.salt_modules_serve_dir / tpl.sls_rel_path
            local_sls_file = SETTINGS.local_repos_dir / tpl.local_path / tpl.sls_rel_path
            logger.debug('Attempting to remove SLS file: %s', serv_sls_file)
            serv_sls_file.unlink(missing_ok=True)
            logger.debug('Attempting to remove SLS file: %s', local_sls_file)
            local_sls_file.unlink(missing_ok=True)
        if tpl.schema_rel_path:
            serv_schema_file = SETTINGS.salt_modules_serve_dir / tpl.schema_rel_path
            local_schema_file = SETTINGS.local_repos_dir / tpl.local_path / tpl.schema_rel_path
            logger.debug('Attempting to remove schema file: %s', serv_schema_file)
            serv_schema_file.unlink(missing_ok=True)
            logger.debug('Attempting to remove schema file: %s', local_schema_file)
            local_schema_file.unlink(missing_ok=True)

    @override
    async def delete_many(
        self,
        query: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            # Remove all related pillars
            tpls = await self.get_list(query=query, session=s, projection_model=TaskTemplateAggregatedModel)
            pillar_query = {
                'tgt_type': PillarTgtType.TASK_TPL,
                'pillarenv': {
                    '$regex': f'task_tpl:{"|".join(map(str, [tpl.id for tpl in tpls]))}.*',
                },
            }
            await self._pillar_repo.delete_many(query=pillar_query, session=s)

            result = await super().delete_many(query=query, session=s)

        for tpl in tpls:
            await self._remove_files(tpl)

        return result

    async def get_with_content(
        self,
        tpl_id: PyObjectId,
        *,
        session: AsyncClientSession | None = None,
    ) -> TaskTemplatePublicWithContentSchema:
        tpl = await self.get(query={'_id': tpl_id}, session=session, projection_model=TaskTemplateAggregatedModel)
        if tpl.source_root:
            path = SETTINGS.local_repos_dir / tpl.local_path / tpl.source_root
        else:
            path = SETTINGS.local_repos_dir / tpl.local_path

        if not tpl.schema_rel_path:
            logger.warning('Template %s does not have a schema file path defined.', tpl_id)
            meta = {}
        else:
            schema_file = path / tpl.schema_rel_path
            logger.debug('Attempting to read schema file: %s', schema_file)
            try:
                meta = json.loads(schema_file.read_text())
            except Exception as e:
                logger.error('Failed to read schema file %s: %s', schema_file, e)
                meta = {}

        if not tpl.sls_rel_path:
            logger.warning('Template %s does not have an SLS file path defined.', tpl_id)
            sls_content = ''
        else:
            sls_file = path / tpl.sls_rel_path
            logger.debug('Attempting to read SLS file: %s', sls_file)
            try:
                sls_content = sls_file.read_text()
            except Exception as e:
                logger.error('Failed to read SLS file %s: %s', sls_file, e)
                sls_content = ''

        return TaskTemplatePublicWithContentSchema.model_validate(
            {
                **tpl.model_dump(),
                'sls_content': sls_content,
                'meta': meta,
                '_id': tpl.id,
            }
        )

    @overload
    async def get_by_name(
        self,
        name: str,
        sid: PyObjectId | None = None,
        *,
        session: AsyncClientSession | None = None,
    ) -> TaskTemplateModel: ...

    @overload
    async def get_by_name(
        self,
        name: str,
        sid: PyObjectId | None = None,
        *,
        session: AsyncClientSession | None = None,
        projection_model: type[ProjectionModel],
    ) -> ProjectionModel: ...

    async def get_by_name(
        self,
        name: str,
        sid: PyObjectId | None = None,
        *,
        session: AsyncClientSession | None = None,
        projection_model: type[ProjectionModel] | None = None,
    ) -> TaskTemplateModel | ProjectionModel:
        if sid is None:
            query: dict[str, str | PyObjectId] = {'name': name}
        else:
            query = {'name': name, 'source_id': sid}

        if projection_model:
            return await self.repo.get(query=query, session=session, projection_model=projection_model)

        return await self.repo.get(query=query, session=session)

    async def get_validated_data(
        self, data: dict, template_id: PyObjectId | None = None, session: AsyncClientSession | None = None
    ) -> dict:
        if template_id is None:
            return data
        try:
            task_template = await self.get(query={'_id': template_id}, session=session)
        except ObjectNotFoundException:
            raise TaskTemplateNotFoundException(template_id=str(template_id)) from None

        Draft4ValidatorWithDefaults(task_template.json_schema).validate(data)

        return data

    async def get_ttl(self, name: str, session: AsyncClientSession | None = None) -> int:
        try:
            template_schema = await self.get_by_name(
                name=name, session=session, projection_model=TaskTemplateDefaultsOnlySchema
            )
        except ObjectNotFoundException:
            return SETTINGS.jobs_default_ttl

        if template_schema.defaults is None or template_schema.defaults.ttl is None:
            return SETTINGS.jobs_default_ttl
        elif template_schema.defaults.ttl == 0:
            return SETTINGS.jobs_max_ttl
        else:
            return template_schema.defaults.ttl

    async def get_schemas_by_names(self, names: list[str]) -> dict[str, dict[str, dict]]:
        for name in names:
            if not await self.exists({'name': name}):
                raise TaskTemplateNotFoundException(template_name=name)
        templates = await self.get_list({'name': {'$in': names}}, projection_model=TaskTemplateSchemasProjection)
        return {
            template.name: {
                'json-schema': template.json_schema,
                'ui-schema': template.ui_schema,
            }
            for template in templates
        }


def get_task_tpl_service(
    repo: Annotated[TaskTemplateRepository, Depends(get_task_template_repository)],
    pillar_repo: Annotated[PillarRepository, Depends(get_pillar_repository)],
) -> TaskTemplateService:
    return TaskTemplateService(repo=repo, pillar_repo=pillar_repo)
