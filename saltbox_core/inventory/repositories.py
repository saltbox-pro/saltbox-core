from collections.abc import Sequence
from typing import ClassVar

from pymongo.operations import UpdateOne

from saltbox_core.inventory.schemas import InventoryCreateSchema, InventoryModel
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import RepositoryException
from saltbox_sdk.utilities import status
from saltbox_sdk.utilities.helpers import utc_now


class BulkOperationsFailedException(RepositoryException):
    """ Bulk execution was not succeed. """

    status_code = status.HTTP_400_BAD_REQUEST
    detail = 'Multiple operations have being failed to commit'


BulkOperation = UpdateOne


class InventoryRepository(BaseMongoRepository[InventoryModel]):
    async def create_indices(self) -> None:
        # await self.collection.create_index('minions')
        await self.collection.create_index('$**')
        # TODO ??? await self.collection.create_index([('name', 1), ('version', 1)], unique=True)

    class Meta:
        # TODO (a.karmanov): <US372> Dynamic
        collection_name = 'inventory'
        auto_now_add_fields: ClassVar[list[str]] = ['created']
        auto_now_fields: ClassVar[list[str]] = ['modified']

    # TODO (a.karmanov): Implement handful methods
    # async def get_by_type(self, value: str) -> list[InventoryModel]:
        # return await self.get(query={'_type': value})

    async def commit(self, operations: Sequence[BulkOperation]) -> list[PyObjectId]:
        bulk_write_result = await self.collection.bulk_write(operations)
        if not bulk_write_result.acknowledged:
            raise BulkOperationsFailedException()
        upserted_ids = bulk_write_result.upserted_ids
        if not upserted_ids:
            return []
        else:
            return [PyObjectId(mongo_id) for mongo_id in upserted_ids.values()]

    def bulk_op_update_or_create(
        self,
        data: InventoryCreateSchema,
    ) -> BulkOperation:
        filter = data.model_dump(exclude={'id'}, exclude_unset=True)
        minions = filter.pop('minions')
        auto_fields: dict = {}

        now = utc_now()

        if hasattr(self.Meta, 'auto_now_fields') and self.Meta.auto_now_fields:
            for field in self.Meta.auto_now_fields:
                auto_fields[field] = now

        if hasattr(self.Meta, 'auto_now_add_fields') and self.Meta.auto_now_add_fields:
            for field in self.Meta.auto_now_add_fields:
                field_val_spec = f'${field}'
                auto_fields[field] = {'$ifNull': [field_val_spec, now]}

        update = [
            {
                '$set': {
                    'tag': {
                        '$ifNull': ['$tag', 'fasion'],
                    },
                    'minions': {
                        '$ifNull': [
                            {
                                '$setUnion': ['$minions', minions],
                            },
                            minions,
                        ]
                    },
                    **auto_fields,
                },
            },
        ]

        return UpdateOne(filter=filter, update=update, upsert=True)
