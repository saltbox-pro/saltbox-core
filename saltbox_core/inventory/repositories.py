from typing import ClassVar

from saltbox_core.inventory.schemas import InventoryModel
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository


class InventoryRepository(BaseMongoRepository[InventoryModel]):
    async def create_indices(self) -> None:
        #await self.collection.create_index('minions')
        await self.collection.create_index('$**')
        # TODO ??? await self.collection.create_index([('name', 1), ('version', 1)], unique=True)

    class Meta:
        collection_name = 'inventory'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']

    # TODO (a.karmanov): Implement handful methods
    #async def get_by_type(self, value: str) -> list[InventoryModel]:
        #return await self.get(query={'_type': value})
