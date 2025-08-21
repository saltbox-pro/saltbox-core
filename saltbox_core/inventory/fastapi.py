from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from saltbox_core.inventory.repositories import InventoryRepository
from saltbox_core.inventory.services import InventoryService
from saltbox_sdk.db.mongo.config import get_mongo


def get_inventory_repository(
    db: Annotated[AsyncDatabase, Depends(get_mongo)]
) -> InventoryRepository:
    return InventoryRepository(db)


InventoryRepositoryDependency = Annotated[InventoryRepository, Depends(get_inventory_repository)]


def get_inventory_service(repo: InventoryRepositoryDependency) -> InventoryService:
    return InventoryService(repo)


InventoryServiceDependency = Annotated[InventoryService, Depends(get_inventory_service)]
