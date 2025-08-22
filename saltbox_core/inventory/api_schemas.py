from pydantic import BaseModel

from saltbox_core.inventory.schemas import InventoryModel


class GetMinionInventoryRequest(BaseModel):
    minion: str
    categories: None | list[str] = None


class GetMinionInventoryResponse(BaseModel):
    data: list[InventoryModel]
