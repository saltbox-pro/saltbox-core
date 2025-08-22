from pydantic import BaseModel

from saltbox_core.inventory.schemas import InventoryBaseModel


class GetMinionInventoryRequest(BaseModel):
    minion: str
    categories: None | list[str] = None


class GetMinionInventoryResponse(BaseModel):
    data: list[InventoryBaseModel]
