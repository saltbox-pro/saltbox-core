import logging
from typing import Annotated

from fastapi import APIRouter, Query

from saltbox_core.inventory.api_schemas import (
    DeleteInventoryRequest,
    GetMinionInventoryRequest,
    GetMinionInventoryResponse,
)
from saltbox_core.inventory.schemas import CATEGORIES, CategoryType
from saltbox_core.inventory.services import get_services_for_categories
from saltbox_sdk.fastapi_utils.dependencies import MongoDependency

logger = logging.getLogger(__name__)
inventory_router = APIRouter(prefix='/inventory', tags=['Inventory'])


@inventory_router.get('')
async def get_inventory_for_minion(
    params: Annotated[GetMinionInventoryRequest, Query()],
    db: MongoDependency,
) -> GetMinionInventoryResponse:  # type: ignore[valid-type]
    categories = params.categories if params.categories else CATEGORIES
    data = {}

    data = {
        service.repo.default_model.category: await service.get_for_minion(minion=params.minion_spec)
        for service in get_services_for_categories(categories=categories, db=db)
    }

    resp = GetMinionInventoryResponse(**data)
    return resp


@inventory_router.get('/categories')
async def get_categories() -> tuple[CategoryType, ...]:
    """ List of known allowed inventory categories """
    return CATEGORIES


@inventory_router.delete('')
async def drop_inventory(
    params: Annotated[DeleteInventoryRequest, Query()],
    db: MongoDependency,
) -> dict[CategoryType, int]:
    """ Drop ALL inventory data! """
    categories = params.categories if params.categories else CATEGORIES
    result = {}

    for service in get_services_for_categories(categories=categories, db=db):
        result[service.category] = await service.delete_many({})
    return result
