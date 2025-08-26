import logging
from collections.abc import Sequence
from functools import cache
from typing import Any

from pymongo.operations import UpdateOne

from saltbox_core.inventory.schemas import InventoryCreateSchemaBase, InventoryModelBase
from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import RepositoryException
from saltbox_sdk.utilities import status
from saltbox_sdk.utilities.helpers import utc_now

logger = logging.getLogger(__name__)


class BulkOperationsFailedException(RepositoryException):
    """ Bulk execution was not succeed. """

    status_code = status.HTTP_400_BAD_REQUEST
    detail = 'Multiple operations have being failed to commit'


BulkOperation = UpdateOne


class InventoryRepositoryBase(BaseMongoRepository):
    """
    Do not use this class directly. Subclass it with:
        class SubType(InventoryModelBase, model: InventoryModelBase = model)
    """
    def __init_subclass__(cls, /, model: InventoryModelBase, **kwargs: dict[str, Any]) -> None:
        super().__init_subclass__(**kwargs)
        meta_members = {
            'collection_name': f'inventory_{model.category}',
            'auto_now_add_fields': ['created'],
            'auto_now_fields': ['modified'],
        }
        cls.Meta = type('Meta', (BaseMongoRepository.Meta,), meta_members)  # type: ignore[assignment, misc]
        cls.default_model = model  # type: ignore[assignment]

    async def create_indices(self) -> None:
        minions_field = 'minions'

        fields = set(self.default_model.model_fields.keys())
        fields.remove(minions_field)
        fields.remove('id')
        for autofield in [*self.Meta.auto_now_fields, *self.Meta.auto_now_add_fields]:
            fields.remove(autofield)
        sorted_fields = sorted(fields)

        await self.collection.create_index([(f, 1) for f in sorted_fields], unique=True, background=True)
        logger.info('Pended index creation for %s fields of %s', sorted_fields, self.Meta.collection_name)
        await self.collection.create_index(minions_field, background=True)
        logger.info('Pended index creation for %s field of %s', minions_field, self.Meta.collection_name)

    async def commit(self, operations: Sequence[BulkOperation]) -> list[PyObjectId]:
        bulk_write_result = await self.collection.bulk_write(operations)
        if not bulk_write_result.acknowledged:
            raise BulkOperationsFailedException()
        upserted_ids = bulk_write_result.upserted_ids
        if not upserted_ids:
            return []
        else:
            return [PyObjectId(mongo_id) for mongo_id in upserted_ids.values()]

    def bulk_op_update_or_create(self, data: InventoryCreateSchemaBase) -> BulkOperation:
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


@cache
def inventory_repository_fab(model: type[InventoryModelBase]) -> type[InventoryRepositoryBase]:
    return type('InventoryRepository', (InventoryRepositoryBase,), {}, model=model)
