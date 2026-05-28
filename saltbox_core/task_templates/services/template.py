from typing import Annotated, Any, override

from fastapi import Depends
from pymongo.asynchronous.client_session import AsyncClientSession

from saltbox_core.config import SETTINGS, logger
from saltbox_core.pillars.repository import PillarRepository, get_pillar_repository
from saltbox_core.pillars.schemas import PillarTgtType
from saltbox_core.task_templates.repositories.template import get_task_template_repository
from saltbox_core.task_templates.schemas.template import (
    TaskTemplateCreateSchema,
    TaskTemplateModel,
    TaskTemplateUpdateSchema,
)
from saltbox_core.tasks.repositories.tasks_template import TaskTemplateRepository
from saltbox_sdk.db.mongo.config import get_mongo_session_with_transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId

# from saltbox_sdk.exceptions import ObjectNotFoundException
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


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
            tpl = await self.get(query=query, session=s)
            pillar_query = {
                'tgt_type': PillarTgtType.TASK_TPL,
                'pillarenv': {
                    '$regex': f'task_tpl:{tpl.id}.*',
                },
            }
            await self._pillar_repo.delete_many(query=pillar_query, session=s)

            result = await super().delete(query=query, session=s)

        sls_file = SETTINGS.salt_modules_serve_dir / tpl.sls_rel_path
        logger.debug('Attempting to remove SLS file: %s', sls_file)
        sls_file.unlink(missing_ok=True)

        return result

    @override
    async def delete_many(
        self,
        query: dict[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        async with get_mongo_session_with_transaction(session) as s:
            # Remove all related pillars
            tpls = await self.get_list(query=query, session=s)
            pillar_query = {
                'tgt_type': PillarTgtType.TASK_TPL,
                'pillarenv': {
                    '$regex': f'task_tpl:{"|".join(map(str, [tpl.id for tpl in tpls]))}.*',
                },
            }
            await self._pillar_repo.delete_many(query=pillar_query, session=s)

            result = await super().delete_many(query=query, session=s)

        for tpl in tpls:
            sls_file = SETTINGS.salt_modules_serve_dir / tpl.sls_rel_path
            logger.debug('Attempting to remove SLS file: %s', sls_file)
            sls_file.unlink(missing_ok=True)

        return result


def get_task_tpl_service(
    repo: Annotated[TaskTemplateRepository, Depends(get_task_template_repository)],
    pillar_repo: Annotated[PillarRepository, Depends(get_pillar_repository)],
) -> TaskTemplateService:
    return TaskTemplateService(repo=repo, pillar_repo=pillar_repo)
