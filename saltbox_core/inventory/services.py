from saltbox_core.inventory.repositories import InventoryRepository
from saltbox_core.inventory.schemas import InventoryCreateSchema, InventoryModel
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class InventoryService(
    MongoBaseService[InventoryRepository, InventoryModel, InventoryCreateSchema, InventoryCreateSchema]
):
    async def bulk_update_or_create(self, data: list[InventoryCreateSchema]) -> None:
        ops = [self.repo.bulk_op_update_or_create(obj) for obj in data]
        await self.repo.commit(ops)
