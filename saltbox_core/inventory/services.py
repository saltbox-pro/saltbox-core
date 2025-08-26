import logging
from collections.abc import Generator, Sequence
from typing import cast

from saltbox_core.inventory.repositories import InventoryRepositoryBase, inventory_repository_fab
from saltbox_core.inventory.schemas import (
    CategoryType,
    InventoryCreateSchemaBase,
    InventoryModelBase,
    InventoryModelFab,
    get_proto_for_category,
)
from saltbox_sdk.db.mongo import MongoAsyncDatabase
from saltbox_sdk.serivces.mongo_base_service import MongoBaseService

logger = logging.getLogger(__name__)


# TODO (a.karmanov): <US372> Cleanup of old data
class InventoryService(
    MongoBaseService[InventoryRepositoryBase, InventoryModelBase, InventoryCreateSchemaBase, InventoryCreateSchemaBase]
):
    async def bulk_update_or_create(self, data: list[InventoryCreateSchemaBase]) -> None:
        ops = [self.repo.bulk_op_update_or_create(obj) for obj in data]
        await self.repo.commit(ops)

    async def get_for_minion(self, minion: str) -> list[InventoryModelBase]:
        query = {'minions': {'$in': [minion]}}
        return await self.get_list(query=query)

    @property
    def category(self) -> CategoryType:
        return cast(CategoryType, self.repo.default_model.category)


def get_service_for_category(category: CategoryType, db: MongoAsyncDatabase) -> InventoryService:
    """
    :raises TypeError: on unknown category
    """
    proto = get_proto_for_category(category)
    model = InventoryModelFab.get_model(proto)
    repo = inventory_repository_fab(model)(db)
    return InventoryService(repo)


def get_services_for_categories(
    categories: Sequence[CategoryType],
    db: MongoAsyncDatabase
) -> Generator[InventoryService]:
    for cat in categories:
        yield get_service_for_category(cat, db=db)


class CachedInventoryServices:
    def __init__(self, db: MongoAsyncDatabase) -> None:
        self.db = db
        self.cache: dict[CategoryType, InventoryService] = {}

    def get(self, category: CategoryType) -> InventoryService:
        """
        :raises TypeError: on unknown category
        """
        service = self.cache.get(category)
        if service is None:
            service = get_service_for_category(category, db=self.db)
            self.cache[category] = service
        return service
