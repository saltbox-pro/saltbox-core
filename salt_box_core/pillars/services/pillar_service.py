import codecs
import csv
from typing import Annotated, BinaryIO

from fastapi import Depends
from redis.asyncio import Redis

from salt_box_core.db.exceptions import ObjectCreateError, ObjectNotFoundError
from salt_box_core.db.redis.config import get_redis
from salt_box_core.masters.services.master_service import MasterService, get_master_service
from salt_box_core.minion_collections.services.minion_service import MinionService, get_minion_service
from salt_box_core.pillars.schemas.pillar_schemas import (
    PillarCSVParseResult,
    PillarCSVParseResultErrorCode,
    PillarImportResultItemSchema,
    PillarImportResultItemStatus,
    PillarImportResultSchema,
    PillarModel,
)
from salt_box_core.pillars.tasks import update_pillar_cache as update_pillar_cache_task

PILLAR_BY_MASTER_HASH_NAME = 'pillar:{master_id}'
PILLAR_BY_MASTER_AND_MINION_HASH_NAME = 'pillar:{master_id}:{minion_id}'


class PillarService:
    def __init__(self, redis_client: Redis, minion_service: MinionService, master_service: MasterService):
        self.redis_client = redis_client
        self.minion_service = minion_service
        self.master_service = master_service

    @staticmethod
    def __get_redis_hash_name(master_id: str, minion_id: str | None = None) -> str:
        if minion_id:
            return PILLAR_BY_MASTER_AND_MINION_HASH_NAME.format(master_id=master_id, minion_id=minion_id)
        else:
            return PILLAR_BY_MASTER_HASH_NAME.format(master_id=master_id)

    @staticmethod
    async def update_pillar_cache(master_id: str, tgt: str | list | None) -> str:
        if tgt is None:
            tgt = '*'
            tgt_type = 'glob'
        elif isinstance(tgt, str):
            tgt_type = 'glob'
        elif isinstance(tgt, list):
            tgt = ','.join(tgt)
            tgt_type = 'list'
        else:
            msg: str = 'tgt must be a None, str or list'  # type: ignore
            raise ValueError(msg)

        task = await update_pillar_cache_task.kiq(master_id=master_id, tgt=tgt, tgt_type=tgt_type)

        return task.task_id

    async def get(self, name: str, master_id: str, minion_id: str | None = None) -> PillarModel:
        pillar_value: bytes | None = await self.redis_client.hget(
            self.__get_redis_hash_name(master_id, minion_id), name
        )

        if not pillar_value:
            if minion_id:
                msg = f'Pillar "{name}" for master "{master_id}" and minion "{minion_id}" not found'
            else:
                msg = f'Pillar "{name}" for master "{master_id}" not found'
            raise ObjectNotFoundError(msg)

        return PillarModel(master_id=master_id, minion_id=minion_id, name=name, value=pillar_value.decode())

    async def exists(self, name: str, master_id: str, minion_id: str | None = None) -> bool:
        return await self.redis_client.hexists(
            self.__get_redis_hash_name(master_id=master_id, minion_id=minion_id), name
        )

    async def get_list(
        self, master_id: str, minion_id: str | None = None, only_for_minion: bool = False
    ) -> list[PillarModel]:
        pillars: list[PillarModel] = []

        async def add_pillar_from_redis(redis_key_pattern: str, mid: str | None = None) -> None:
            redis_key = redis_key_pattern.format(master_id=master_id, minion_id=mid)
            pillar_data = await self.redis_client.hgetall(redis_key)
            for pillar_name, pillar_value in pillar_data.items():
                pillars.append(
                    PillarModel(master_id=master_id, minion_id=mid, name=pillar_name, value=pillar_value.decode())
                )

        if not only_for_minion:
            await add_pillar_from_redis(PILLAR_BY_MASTER_HASH_NAME)

        if minion_id:
            await add_pillar_from_redis(PILLAR_BY_MASTER_AND_MINION_HASH_NAME, minion_id)
        elif not only_for_minion:
            for pillars_redis_key_bytes in await self.redis_client.keys(
                PILLAR_BY_MASTER_AND_MINION_HASH_NAME.format(master_id=master_id, minion_id='*')
            ):
                pillars_redis_key = pillars_redis_key_bytes.decode()
                await add_pillar_from_redis(pillars_redis_key, pillars_redis_key.split(':')[-1])

        return pillars

    async def create(
        self, name: str, value: str, master_id: str, minion_id: str | None = None, update_pillar_cache: bool = True
    ) -> PillarModel:
        try:
            await self.master_service.get_by_master_id(master_id=master_id)
        except ObjectNotFoundError as e:
            msg = f'Master "{master_id}" does not exist'
            raise ValueError(msg) from e

        if not minion_id or minion_id == '*':
            query = {'master': master_id}
        else:
            query = {'minion_id': minion_id, 'master': master_id}

        if master_id and not await self.minion_service.exists(query):
            msg = f'Minion "{minion_id}" from master "{master_id}" does not exist'
            raise ValueError(msg)

        hash_name = self.__get_redis_hash_name(master_id=master_id, minion_id=minion_id)

        if await self.redis_client.hexists(hash_name, name):
            if minion_id:
                msg = f'Pillar "{name}" for master "{master_id}" and minion "{minion_id}" already exists'
            else:
                msg = f'Pillar "{name}" for master "{master_id}" already exists'
            raise ObjectCreateError(msg)

        await self.redis_client.hset(hash_name, name, value)

        if update_pillar_cache:
            await self.update_pillar_cache(master_id=master_id, tgt=minion_id)

        return PillarModel(master_id=master_id, minion_id=minion_id, name=name, value=value)

    async def update(
        self, name: str, value: str, master_id: str, minion_id: str | None = None, update_pillar_cache: bool = True
    ) -> PillarModel:
        hash_name = self.__get_redis_hash_name(master_id=master_id, minion_id=minion_id)

        if not await self.redis_client.hexists(hash_name, name):
            if minion_id:
                msg = f'Pillar "{name}" for master "{master_id}" and minion "{minion_id}" not found'
            else:
                msg = f'Pillar "{name}" for master "{master_id}" not found'
            raise ObjectNotFoundError(msg)

        await self.redis_client.hset(hash_name, name, value)

        if update_pillar_cache:
            await self.update_pillar_cache(master_id=master_id, tgt=minion_id)

        return PillarModel(master_id=master_id, minion_id=minion_id, name=name, value=value)

    async def update_or_create(
        self, name: str, value: str, master_id: str, minion_id: str | None = None, update_pillar_cache: bool = True
    ) -> PillarModel:
        try:
            return await self.update(
                name=name,
                value=value,
                master_id=master_id,
                minion_id=minion_id,
                update_pillar_cache=update_pillar_cache,
            )
        except ObjectNotFoundError:
            return await self.create(
                name=name,
                value=value,
                master_id=master_id,
                minion_id=minion_id,
                update_pillar_cache=update_pillar_cache,
            )

    async def delete(self, name: str, master_id: str, minion_id: str | None = None) -> None:
        hash_name = self.__get_redis_hash_name(master_id=master_id, minion_id=minion_id)

        if not await self.redis_client.hexists(hash_name, name):
            if minion_id:
                msg = f'Pillar "{name}" for master "{master_id}" and minion "{minion_id}" not found'
            else:
                msg = f'Pillar "{name}" for master "{master_id}" not found'
            raise ObjectNotFoundError(msg)

        await self.redis_client.hdel(hash_name, name)

        return None

    async def get_parse_item_result(
        self, master_id: str, minion_id: str | None, pillar_name: str, pillar_value: str
    ) -> PillarCSVParseResult:
        error_codes = []

        try:
            await self.master_service.get_by_master_id(master_id=master_id)
        except ObjectNotFoundError:
            error_codes.append(PillarCSVParseResultErrorCode.master_does_not_exist)

        if not await self.minion_service.exists({'minion_id': minion_id, 'master': master_id}):
            error_codes.append(PillarCSVParseResultErrorCode.minion_does_not_exist)

        if await self.exists(master_id=master_id, minion_id=minion_id, name=pillar_name):
            error_codes.append(PillarCSVParseResultErrorCode.pillar_already_exists)

        return PillarCSVParseResult(
            master_id=master_id,
            minion_id=minion_id,
            name=pillar_name,
            value=pillar_value,
            error_codes=error_codes,
        )

    async def parse_csv(self, master_id: str, file: BinaryIO) -> list[PillarCSVParseResult]:
        csv_reader = csv.DictReader(codecs.iterdecode(file, 'utf-8'))
        result: list[PillarCSVParseResult] = []

        for row in csv_reader:
            minion_id = row['minion_id']

            for pillar_name, pillar_value in row.items():
                if pillar_name == 'minion_id':
                    continue

                result.append(
                    await self.get_parse_item_result(
                        master_id=master_id, minion_id=minion_id, pillar_name=pillar_name, pillar_value=pillar_value
                    )
                )

        return result

    async def validate_import_date(self, items: list[PillarModel]) -> list[PillarCSVParseResult]:
        result: list[PillarCSVParseResult] = []

        for item in items:
            result.append(
                await self.get_parse_item_result(
                    master_id=item.master_id, minion_id=item.minion_id, pillar_name=item.name, pillar_value=item.value
                )
            )

        return result

    async def import_pillar(self, items: list[PillarModel], update_existing: bool = False) -> PillarImportResultSchema:
        result: PillarImportResultSchema = PillarImportResultSchema()
        minions_updated: dict[str, set[str]] = {}

        for item in items:
            item_exists: bool = await self.exists(master_id=item.master_id, minion_id=item.minion_id, name=item.name)

            if item_exists and not update_existing:
                result.items.append(
                    PillarImportResultItemSchema(**item.model_dump(), status=PillarImportResultItemStatus.skipped)
                )
                result.skipped += 1
                continue

            try:
                pillar: PillarModel = await self.update_or_create(**item.model_dump(), update_pillar_cache=False)
                result.items.append(PillarImportResultItemSchema(**pillar.model_dump()))
                if item.minion_id:
                    minions_updated.setdefault(item.master_id, set()).add(item.minion_id)
                else:
                    minions_updated.setdefault(item.master_id, set())
                result.succeed += 1
            except (ObjectCreateError, ValueError) as e:
                result.items.append(
                    PillarImportResultItemSchema(
                        **item.model_dump(), status=PillarImportResultItemStatus.fail, error_text=str(e)
                    )
                )
                result.failed += 1

        for master_id, minions in minions_updated.items():
            await self.update_pillar_cache(master_id=master_id, tgt=list(minions) if len(minions) else None)

        return result


def get_pillar_service(
    redis_client: Annotated[Redis, Depends(get_redis)],
    minion_service: Annotated[MinionService, Depends(get_minion_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> PillarService:
    return PillarService(redis_client=redis_client, minion_service=minion_service, master_service=master_service)
