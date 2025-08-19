from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class InventoryCreateSchema(BaseModel):
    model_config = ConfigDict(extra='allow')

    object_type: str = Field(description='Kind of inventory data')
    minions: list[str] = Field(description='Relation with minions')


class InventoryModel(InventoryCreateSchema, IDMixin, CreatedModifiedMixin):
    model_config = ConfigDict(extra='allow')
