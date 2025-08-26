from pydantic import BaseModel

from saltbox_core.inventory.schemas import CategoryType, InventoryModelBase


class GetMinionInventoryRequest(BaseModel):
    minion: str
    categories: None | list[CategoryType] = None


class GetMinionInventoryResponse(BaseModel):
    data: dict[CategoryType, list[InventoryModelBase]]
