from typing import Any

from pydantic import BaseModel, ConfigDict

from saltbox_sdk.db.mongo.schemas_base import IDMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class MinionExtraDataItemReadOnlyFieldsMixin(BaseModel):
    name: str
    source: str
    value: Any


class MinionExtraDataItemEditableFieldsMixin(BaseModel): ...


class MinionExtraDataItemCreateSchema(MinionExtraDataItemEditableFieldsMixin, MinionExtraDataItemReadOnlyFieldsMixin):
    pass


class MinionExtraDataItemUpdateSchema(MinionExtraDataItemEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class MinionExtraDataItemModel(
    IDMixin,
    CreatedModifiedMixin,
    MinionExtraDataItemEditableFieldsMixin,
    MinionExtraDataItemReadOnlyFieldsMixin,
): ...
