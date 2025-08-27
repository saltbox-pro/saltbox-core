from typing import Any

from pydantic import BaseModel, create_model

from saltbox_core.inventory.schemas import (
    CATEGORIES,
    CategoryType,
    InventoryModelFab,
    get_proto_for_category,
)


class GetMinionInventoryRequest(BaseModel):
    minion: str
    categories: None | list[CategoryType] = None


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
