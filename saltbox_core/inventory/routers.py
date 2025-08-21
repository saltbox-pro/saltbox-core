import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from saltbox_core.inventory.fastapi import InventoryServiceDependency
from saltbox_core.inventory.schemas import InventoryModel

logger = logging.getLogger(__name__)
inventory_router = APIRouter(prefix='/inventory', tags=['Inventory'])


class GetMinionInventoryRequest(BaseModel):
    minion: str
    categories: None | list[str] = None


class GetMinionInventoryResponse(BaseModel):
    data: list[InventoryModel]


@inventory_router.get('')
async def get_inventory_for_minion(
    params: Annotated[GetMinionInventoryRequest, Query()],
    inventory_service: InventoryServiceDependency,
) -> GetMinionInventoryResponse:
    query = {'minions': {'$in': [params.minion]}}
    if params.categories is not None:
        query['object_type'] = {'$in': params.categories}
    data = await inventory_service.get_list(query=query)
    resp = GetMinionInventoryResponse(data=data)
    return resp
