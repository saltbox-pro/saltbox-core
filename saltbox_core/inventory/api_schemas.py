from typing import Any

from pydantic import BaseModel, Field, create_model

from saltbox_core.inventory.schemas import (
    CATEGORIES,
    CategoryType,
    InventoryMinionSpec,
    InventoryModelFab,
    get_proto_for_category,
)


class GetMinionInventoryRequest(BaseModel):
    master_id: str
    minion_id: str
    categories: None | list[CategoryType] = None

    @property
    def minion_spec(self) -> InventoryMinionSpec:
        return InventoryMinionSpec(master_id=self.master_id, minion_id=self.minion_id)


def _make_minion_inventory_resp(name: str) -> type[BaseModel]:
    models = (
        InventoryModelFab.get_model(get_proto_for_category(cat))
        for cat in CATEGORIES
    )

    # TODO (a.karmanov): <US372> `Field(exclude_if=lamda x : x is None)` in Pydantic 2.12
    fields: dict[str, Any] = {
        mod.category: (list[mod] | None, None)  # type: ignore[valid-type]
        for mod in models
    }

    return create_model(name, **fields)


GetMinionInventoryResponse = _make_minion_inventory_resp('GetMinionInventoryResponse')


class DeleteInventoryRequest(BaseModel):
    categories: None | list[CategoryType] = Field(
        None,
        description='Categories to drop, ALL if not specified',
    )
