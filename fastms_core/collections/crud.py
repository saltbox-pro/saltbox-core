from fastms_core.collections.models import MinionCollection
from fastms_core.collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListSchema,
    MinionCollectionUpdateSchema,
)
from fastms_core.db.mongo.crud_base import CRUDBase


class CRUDMinionCollection(
    CRUDBase[MinionCollection, MinionCollectionListSchema, MinionCollectionCreateSchema, MinionCollectionUpdateSchema]
):
    pass


collections_crud = CRUDMinionCollection(MinionCollection)
