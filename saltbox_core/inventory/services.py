from saltbox_core.inventory.repositories import InventoryRepository
from saltbox_core.inventory.schemas import InventoryBaseModel, InventoryCreateSchema
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class InventoryService(
    MongoBaseService[InventoryRepository, InventoryBaseModel, InventoryCreateSchema, InventoryCreateSchema]
):
    async def bulk_update_or_create(self, data: list[InventoryCreateSchema]) -> None:
        ops = [self.repo.bulk_op_update_or_create(obj) for obj in data]
        await self.repo.commit(ops)

    async def get_for_minion(self, minion: str, categories: None | list[str] = None) -> list[InventoryBaseModel]:
        # TODO (a.karmanov): <US372> Categories typing
        query = {'minions': {'$in': [minion]}}
        if categories is not None:
            query['object_type'] = {'$in': categories}
        return await self.get_list(query=query)
