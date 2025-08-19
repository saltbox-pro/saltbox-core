from saltbox_core.inventory.repositories import InventoryRepository
from saltbox_core.inventory.schemas import InventoryCreateSchema, InventoryModel
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService


class InventoryService(
    MongoBaseService[InventoryRepository, InventoryModel, InventoryCreateSchema, InventoryCreateSchema]
):
    ...
