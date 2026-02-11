from typing import Annotated, ClassVar, override

from fastapi import Depends
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.operations import _IndexKeyHint

from saltbox_core.config import logger
from saltbox_core.pillars.schemas import PillarCreateSchema, PillarModel, PillarTgtType
from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class PillarRepository(BaseMongoRepository[PillarModel]):
    class Meta:
        collection_name = 'pillars'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']
        collection_index_to_keys: ClassVar[dict[str, _IndexKeyHint]] = {
            'tgt_name_unique_index_asc': [
                ('tgt_type', ASCENDING),
                ('tgt_id', ASCENDING),
                ('name', ASCENDING),
                ('pillarenv', ASCENDING),
            ],
        }

    @override
    async def _post_create_collection(self) -> None:
        root_collection: dict = await self._BaseMongoRepository__database['minion_collections'].find_one(  # type: ignore[attr-defined]
            {'slug': 'root'}, {'_id': 1}
        )
        root_id = root_collection.get('_id') if root_collection else None
        is_test_pillar_exists = await self.exists(
            query={
                'name': 'test',
                'tgt_type': PillarTgtType.ROOT,
                'tgt_id': root_id,
                'pillarenv': 'base',
            }
        )
        logger.debug('Root collection ID: %s', root_id)
        if not root_id:
            logger.error('Root collection not found. Cannot create test pillar.')
            return
        if not is_test_pillar_exists:
            logger.debug('Creating test pillar')
            test_pillar = PillarCreateSchema(
                name='test',
                tgt_type=PillarTgtType.ROOT,
                tgt_id=root_id,
                is_personal=False,
                pillarenv='base',
                value='This is a test pillar value',
                created_by={'sub': 'system', 'username': 'system'},
            )
            created_pillar = await self.create(data=test_pillar)
            logger.info('Created test pillar: %s', created_pillar)
        else:
            logger.debug('Test pillar already exists')


def get_pillar_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> PillarRepository:
    return PillarRepository(database=db)
