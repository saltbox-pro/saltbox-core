import re
from typing import Annotated, Any

from fastapi import Depends
from pydantic import JsonValue
from pymongo.asynchronous.client_session import AsyncClientSession as MongoAsyncClientSession

from saltbox_core.config import logger
from saltbox_core.minion_collections.schemas.minion import MinionTgtOnlySchema
from saltbox_core.minion_collections.services.collection import CollectionService, get_collection_service
from saltbox_core.minion_collections.services.minion import MinionService, get_minion_service
from saltbox_core.pillars.exceptions import (
    PillarCreatedByRequiredException,
    PillarTargetIdRequiredException,
    PillarTgtNotFoundException,
    PillarUpdateSecretNotAllowedException,
)
from saltbox_core.pillars.repository import PillarRepository, get_pillar_repository
from saltbox_core.pillars.schemas import (
    PillarCreateSchema,
    PillarModel,
    PillarTgtType,
    PillarUpdateSchema,
)
from saltbox_core.pillars.services.pillar_crypto import PillarCryptoService, get_pillar_crypto_service
from saltbox_sdk.db.mongo.repository_base import MongoUpdateOperator
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.db.schemas_base import UserShort
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class PillarService(MongoBaseService[PillarRepository, PillarModel, PillarCreateSchema, PillarUpdateSchema]):
    # Regex for collection:<PyObjectId>;user:<sub>
    _COLLECTION_ID_USER_ID_REGEX = re.compile(r'collection:(?P<collection_id>[a-f0-9]{24});user:(?P<user_sub>[^;]+)')
    # Regex for minion:<PyObjectId>;user:<sub>
    _MINION_ID_REGEX = re.compile(r'minion:(?P<minion_id>[a-f0-9]{24})')
    # Regex for task_tpl:<PyObjectId>;user:<sub>
    _TASK_TPL_ID_REGEX = re.compile(r'task_tpl:(?P<task_tpl_id>[a-f0-9]{24})')
    # Regex for task:<PyObjectId>;user:<sub>
    _TASK_ID_REGEX = re.compile(r'task:(?P<task_id>[a-f0-9]{24})')
    _USER_ID_REGEX = re.compile(r'user:(?P<user_id>[^;]+)')

    def __init__(
        self,
        repo: PillarRepository,
        collection_service: CollectionService,
        minion_service: MinionService,
        crypto_service: PillarCryptoService,
    ):
        super().__init__(repo=repo)
        self._collection_service = collection_service
        self._minion_service = minion_service
        self._crypto_service = crypto_service

    async def create(
        self,
        data: PillarCreateSchema | dict[str, Any],
        *,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        if not isinstance(data, PillarCreateSchema):
            data = PillarCreateSchema.model_validate(data)
        if not data.created_by:
            raise PillarCreatedByRequiredException()

        data.tgt_id, data.pillarenv = await self._resolve_target(data)
        data.value = self._crypto_service.encrypt_if_needed(data)

        return await super().create(data=data, session=session)

    async def update(
        self,
        query: dict[str, Any] | PyObjectId,
        data: PillarUpdateSchema | dict[str, Any],
        exclude_unset: bool = True,
        *,
        operator: MongoUpdateOperator = MongoUpdateOperator.set,
        session: MongoAsyncClientSession | None = None,
    ) -> PyObjectId:
        if isinstance(query, PyObjectId):
            query = {'_id': query}
        pillar = await self.get(query=query, session=session)
        if self._crypto_service.is_encrypted(pillar):
            raise PillarUpdateSecretNotAllowedException()

        return await super().update(
            query=query, data=data, exclude_unset=exclude_unset, operator=operator, session=session
        )

    async def _resolve_target(self, data: PillarCreateSchema) -> tuple[PyObjectId, str]:
        if not data.created_by:
            raise PillarCreatedByRequiredException()

        if data.tgt_type == PillarTgtType.ROOT:
            return await self._collection_service.get_root_collection_id(), 'base'

        if not data.tgt_id:
            raise PillarTargetIdRequiredException()

        tgt_id: PyObjectId = data.tgt_id

        match data.tgt_type:
            case PillarTgtType.MINION:
                minion = await self._minion_service.get(query={'_id': tgt_id}, projection_model=MinionTgtOnlySchema)
                if not minion:
                    raise PillarTgtNotFoundException()
                return tgt_id, f'minion_id:{minion.minion_id};master:{minion.master}'
            case PillarTgtType.COLLECTION:
                if not await self._collection_service.exists(query={'_id': tgt_id}):
                    raise PillarTgtNotFoundException()
                return tgt_id, f'{data.tgt_type}:{tgt_id};user:{data.created_by.sub}'
            case PillarTgtType.TASK:
                return tgt_id, f'{data.tgt_type}:{tgt_id}'
            case PillarTgtType.TASK_TPL:
                return tgt_id, f'{data.tgt_type}:{tgt_id};user:{data.created_by.sub}'
            case _:
                raise PillarTgtNotFoundException()

    async def get_merged(self, master: str, minion_id: str, pillarenv: str = 'base') -> dict[str, JsonValue]:
        merge_result = {}
        envs = [e.strip() for e in pillarenv.split(',')]
        for env in envs:
            if env.startswith('collection:'):
                m = self._COLLECTION_ID_USER_ID_REGEX.search(env)
                collection_id = m.group('collection_id') if m else None
                user_sub = m.group('user_sub') if m else None
                if collection_id and await self._collection_service.exists(query={'_id': PyObjectId(collection_id)}):
                    branch_ids = await self._collection_service.repo.get_ancestors_ids(
                        target=PyObjectId(collection_id), include_self=True
                    )
                    for collection_id in branch_ids:
                        env_for_collection = (
                            f'collection:{collection_id};user:{user_sub}' if user_sub else f'collection:{collection_id}'
                        )
                        pillars = await self.get_list(query={'pillarenv': env_for_collection})
                        merge_result.update(
                            {pillar.name: self._crypto_service.decrypt_if_needed(pillar) for pillar in pillars}
                        )

            pillars = await self.get_list(query={'pillarenv': env})
            try:
                merge_result.update({pillar.name: self._crypto_service.decrypt_if_needed(pillar) for pillar in pillars})
            except Exception as e:
                logger.error(f'Error decrypting pillars for env {env}: {e}')
        # Get base pillars for minion:<minion_id> if exists, because it has the highest priority
        if 'base' in envs:
            minion_base_pillars = await self.get_list(query={'pillarenv': f'minion_id:{minion_id};master:{master}'})
            merge_result.update(
                {pillar.name: self._crypto_service.decrypt_if_needed(pillar) for pillar in minion_base_pillars}
            )
        return merge_result

    async def create_for_task(
        self,
        *,
        task_id: PyObjectId,
        pillars: dict[str, JsonValue],
        user: UserShort,
        secret_pillar_names: list[str] | None = None,
        task_template_id: PyObjectId | None = None,
        save_as_default: bool = False,
        session: MongoAsyncClientSession | None = None,
    ) -> None:
        # TODO: maybe need to be removed
        deleted_count = await self.delete_many(
            query={
                '$or': [
                    {'tgt_type': PillarTgtType.TASK, 'tgt_id': task_id},
                    {'pillenv': f'task:{task_id}'},
                ]
            },
            session=session,
        )
        logger.debug(f'Deleted {deleted_count} existing pillars for task {task_id}')

        if secret_pillar_names and task_template_id:
            default_secret_pillars = await self.get_list(
                query={
                    'tgt_type': PillarTgtType.TASK_TPL,
                    'tgt_id': task_template_id,
                    'is_secret': True,
                },
                session=session,
            )

        new_pillars_data = []
        created_for_task_count = 0
        for name, value in pillars.items():
            is_secret = secret_pillar_names is not None and name in secret_pillar_names

            logger.debug(f'Processing pillar "{name}" for task {task_id} with value: {value} and is_secret={is_secret}')

            if is_secret and value == '*******' and task_template_id:
                default_pillar = next((p for p in default_secret_pillars if p.name == name), None)
                if default_pillar:
                    value = self._crypto_service.decrypt_if_needed(default_pillar)
            pillar_data = {
                'name': name,
                'value': value,
                'is_secret': is_secret,
                'created_by': user,
            }
            new_pillars_data.append(pillar_data)
            pillar_create = PillarCreateSchema(
                tgt_type=PillarTgtType.TASK,
                tgt_id=task_id,
                pillarenv=f'task:{task_id}',
                **pillar_data,
            )
            await self.create(data=pillar_create, session=session)
            created_for_task_count += 1
        logger.debug(f'Created {created_for_task_count} pillars for task {task_id}')

        if save_as_default:
            logger.debug(f'Tryng to save pillars as default for task template {task_template_id}')
            deleted_count = await self.delete_many(
                query={
                    'tgt_type': PillarTgtType.TASK_TPL,
                    'tgt_id': task_template_id,
                },
                session=session,
            )
            logger.debug(f'Deleted {deleted_count} existing default pillars for task template {task_template_id}')
            created_for_tpl_count = 0
            for pillar_data in new_pillars_data:
                pillar_create = PillarCreateSchema(
                    tgt_type=PillarTgtType.TASK_TPL,
                    tgt_id=task_template_id,
                    pillarenv=f'task_tpl:{task_template_id};user:{user.sub}',
                    **pillar_data,
                )
                await self.create(data=pillar_create, session=session)
                created_for_tpl_count += 1
            logger.debug(f'Created {created_for_tpl_count} default pillars for task template {task_template_id}')

    async def get_for_target(
        self, tgt_type: PillarTgtType, tgt_id: PyObjectId, user_sub: str | None = None
    ) -> dict[str, JsonValue]:
        user_env = f'user:{user_sub}' if user_sub else ''
        tgt_env = f'{tgt_type}:{tgt_id}'
        pillarenv = f'{tgt_env};{user_env}' if user_env else tgt_env

        pillars = await self.get_list(query={'pillarenv': pillarenv})
        return {pillar.name: self._crypto_service.decrypt_if_needed(pillar) for pillar in pillars}


def get_pillar_service(
    repo: Annotated[PillarRepository, Depends(get_pillar_repository)],
    collection_service: Annotated[CollectionService, Depends(get_collection_service)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    crypto_service: Annotated[PillarCryptoService, Depends(get_pillar_crypto_service)],
) -> PillarService:
    return PillarService(
        repo=repo,
        collection_service=collection_service,
        minion_service=minion_service,
        crypto_service=crypto_service,
    )
