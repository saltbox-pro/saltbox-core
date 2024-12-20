import logging.config

from fastms_core.collections.models import MinionCollection
from fastms_core.collections.schemas import (
    MinionCollectionCreateSchema,
    MinionCollectionListSchema,
    MinionCollectionUpdateSchema,
)
from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.crud_base import CRUDBase

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CRUDMinionCollection(
    CRUDBase[MinionCollection, MinionCollectionListSchema, MinionCollectionCreateSchema, MinionCollectionUpdateSchema]
):
    pass


collections_crud = CRUDMinionCollection(MinionCollection)
