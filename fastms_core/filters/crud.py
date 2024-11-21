import logging.config

from fastms_core.config import LOG_CONFIG
from fastms_core.db.mongo.crud_base import CRUDBase
from fastms_core.filters.models import Filter
from fastms_core.filters.schemas import FilterListSchema, FilterCreateSchema, FilterUpdateSchema

logging.config.dictConfig(LOG_CONFIG.model_dump())

logger = logging.getLogger(__name__)


class CRUDMinion(CRUDBase[Filter, FilterListSchema, FilterCreateSchema, FilterUpdateSchema]):
    pass


filter_crud = CRUDMinion(Filter)
