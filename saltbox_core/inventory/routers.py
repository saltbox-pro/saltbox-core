import logging
from typing import Annotated

from fastapi import APIRouter, Query

from saltbox_core.inventory.api_schemas import GetMinionInventoryRequest, GetMinionInventoryResponse
from saltbox_core.inventory.fastapi import InventoryServiceDependency

logger = logging.getLogger(__name__)
inventory_router = APIRouter(prefix='/inventory', tags=['Inventory'])


# TODO: (a.karmanov) <US439> FIXME list params
@inventory_router.get('')
async def get_inventory_for_minion(
    params: Annotated[GetMinionInventoryRequest, Query()],
    inventory_service: InventoryServiceDependency,
) -> GetMinionInventoryResponse:
    data = await inventory_service.get_for_minion(minion=params.minion, categories=params.categories)
    resp = GetMinionInventoryResponse(data=data)
    return resp
