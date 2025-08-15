from datetime import UTC, datetime
from typing import Any

from faststream import Context
from faststream.redis import RedisRouter

from saltbox_bridge_messages import (
    BridgeAuthRequest,
    BridgeInventoryDataSavedMessage,
    BridgeMinionGrainsMessage,
    BridgeMinionPresenceMessage,
    BridgeSyncDoneMessage,
    BridgeTestBurstLoadMessage,
    CoreAuthResponse,
    MasterStatus,
)
from saltbox_core.config import logger
from saltbox_core.event_bus.redis.master_bus_middlewares import MastersAuthMiddleware
from saltbox_core.jobs.services.job_services import JobServiceDependency
from saltbox_core.masters.schemas.master_schemas import MasterCreateSchema, MasterModel
from saltbox_core.masters.services.master_service import MasterService
from saltbox_core.minion_collections.schemas.minion_schemas import (
    GrainsSchema,
    MinionCreateSchema,
    MinionModel,
    MinionUpdateSchema,
)
from saltbox_core.minion_collections.services.minion_service import MinionService
from saltbox_core.utilities.gpg import SaltBoxCrypt
from saltbox_core.utilities.jid import JID, JidError
from saltbox_sdk.exceptions import ObjectNotFoundException

router_not_auth = RedisRouter(prefix='master_', middlewares=[])
router = RedisRouter(prefix='master_', middlewares=[MastersAuthMiddleware])


@router_not_auth.subscriber('auth', middlewares=[])
async def auth(
    message: BridgeAuthRequest,
    master_service: MasterService = Context(),  # noqa: B008
    saltbox_crypt: SaltBoxCrypt = Context(),  # noqa: B008
) -> CoreAuthResponse:
    try:
        master: MasterModel = await master_service.get_by_master_id(message.master)
    except ObjectNotFoundException:
        create = MasterCreateSchema(
            master_id=message.master,
            title=message.master,
            salt_conf_pubkey=message.salt_conf_pubkey,
            sshfs_pubkey=message.sshfs_pubkey,
            pubkey=message.crypt_pubkey,
        )
        master = await master_service.create(create)
    else:
        if master.status is MasterStatus.KEYS_STALE:
            master.status = MasterStatus.NEW
            master.pubkey = message.crypt_pubkey
            master.salt_conf_pubkey = message.salt_conf_pubkey
            master.sshfs_pubkey = message.sshfs_pubkey
            master = await master_service.update(query=master.id, data=master.model_dump())

    return CoreAuthResponse(
        master=master.master_id,
        crypt_pubkey=saltbox_crypt.pubkey,
        status=master.status,
    )


@router.subscriber('sync_saltbox_done')
async def sync_saltbox_done(
    message: BridgeSyncDoneMessage,
    master_service: MasterService = Context(),  # noqa: B008
) -> None:
    master = await master_service.get_by_master_id(message.master)
    master.last_sync_timestamp = message.time
    master.last_sync_status = message.status
    await master_service.update(query=master.id, data=master.model_dump())


@router.subscriber('grains')
async def grains_handler(
    message: BridgeMinionGrainsMessage,
    minion_service: MinionService = Context(),  # noqa: B008
) -> None:
    grains = message.grains
    minion_id = grains['id']

    if grains:
        try:
            minion: MinionModel = await minion_service.get_by_master_and_id(master=message.master, minion_id=minion_id)
            minion.grains = GrainsSchema(**grains)
            await minion_service.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
        except ObjectNotFoundException:
            minion_obj = {
                'minion_id': minion_id,
                'master': message.master,
                'grains': grains,
            }
            await minion_service.create(MinionCreateSchema(**minion_obj))


@router.subscriber('presence')
async def presence_handler(
    message: BridgeMinionPresenceMessage,
    minion_service: MinionService = Context(),  # noqa: B008
) -> None:
    last_activity_dt = datetime.fromtimestamp(message.stamp, tz=UTC)

    for minion_id in message.minions:
        try:
            minion: MinionModel = await minion_service.get_by_master_and_id(master=message.master, minion_id=minion_id)
            minion.last_activity = last_activity_dt
            await minion_service.update(minion.id, MinionUpdateSchema(**minion.model_dump()))
        except ObjectNotFoundException:
            logger.info('Minion "%s" from presence not found in DB', minion_id)


@router.subscriber('burst_test_load')
async def burst_test_load_handler(message: BridgeTestBurstLoadMessage) -> None:
    # TODO (a.karmanov) : Count burst rate and save to DB
    ...


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def solve_path(path: list[str | int], obj: object) -> Any:
    current = obj
    for key in path:
        try:
            if hasattr(current, '__getitem__'):
                current = current[key]
            else:
                current = getattr(current, key)  # type: ignore[arg-type]
        except (IndexError, KeyError, TypeError, AttributeError) as err:
            path_repr = []
            for i in path:
                path_repr.append(f'[{i}]' if isinstance(i, int) else i)
            logger.error('Failed to follow path "%s" on "%s"', '.'.join(path_repr), key)
            raise ValueError(err) from err
    return current

import asyncio
from typing import Annotated, ClassVar

from faststream import Depends
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_sdk.db.mongo.config import get_mongo
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class InventoryCreateSchema(BaseModel):
    model_config = ConfigDict(extra='allow')

    object_type: str = Field(description='Kind of inventory data')
    minions: list[str] = Field(description='Relation with minions')


class InventoryModel(InventoryCreateSchema, IDMixin, CreatedModifiedMixin):
    model_config = ConfigDict(extra='allow')


class InventoryRepository(BaseMongoRepository[InventoryModel]):
    async def create_indices(self) -> None:
        await self.collection.create_index('minions')
        # TODO ??? await self.collection.create_index([('name', 1), ('version', 1)], unique=True)

    class Meta:
        collection_name = 'inventory'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']

    # TODO (a.karmanov): Implement handful methods
    #async def get_by_type(self, value: str) -> list[InventoryModel]:
        #return await self.get(query={'_type': value})


class InventoryService(
    MongoBaseService[InventoryRepository, InventoryModel, InventoryCreateSchema, InventoryCreateSchema]
):
    ...


def get_inventory_repository(db: Annotated[AsyncDatabase, Depends(get_mongo)]) -> InventoryRepository:
    return InventoryRepository(db)


def get_inventory_service(repo: Annotated[InventoryRepository, Depends(get_inventory_repository)]) -> InventoryService:
    return InventoryService(repo)



@router.subscriber('inventory_saved')
async def inventory_handler(
    message: BridgeInventoryDataSavedMessage,
    job_service: JobServiceDependency = Context(),
    # TODO Depends inventory_service: InventoryService = Depends(get_inventory_service),
    inventory_service: InventoryService = Context(),
) -> None:
    jid = JID(message.jid)

    for mid in message.minions:
        result = await job_service.get_job_return_for_minion(jid, mid)
        if result is not None:
            inventory = solve_path(message.path, result.model_dump(by_alias=True))
            for inv_type, inv_list in inventory.items():
                for inv_item in inv_list:
                    ...
                      #update = {'$addToSet': {'_minions': minion['_id']}}
                      #ops.append(UpdateOne(filter=soft, update=update, upsert=True))

                    obj = InventoryCreateSchema(
                        **inv_item,
                        object_type=inv_type,
                        minions=[mid]
                    )
                    await inventory_service.create(obj)
        else:
            logger.warn('Not found inventory for minion %s, JID=%s', mid, jid)
