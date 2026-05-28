from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class ExtraDataReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    data: Any = Field(title='Data')
    minions: dict[PyObjectId, Any] = Field(title='Minions data', default_factory=dict)


class ExtraDataEditableFieldsMixin(BaseModel): ...


class ExtraDataCreateSchema(ExtraDataEditableFieldsMixin, ExtraDataReadOnlyFieldsMixin):
    pass


class ExtraDataUpdateSchema(ExtraDataEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class ExtraDataModel(
    IDMixin,
    CreatedModifiedMixin,
    ExtraDataEditableFieldsMixin,
    ExtraDataReadOnlyFieldsMixin,
): ...
