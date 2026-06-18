from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class ExtraDataForMinion(BaseModel):
    minion_id: PyObjectId = Field(title='Minion MongoDB id')
    data: dict = Field(title='Minion data')


class ExtraDataReadOnlyFieldsMixin(BaseModel):
    source: str = Field(title='Source')
    name: str = Field(title='Name')
    data: Any = Field(title='Data')


class ExtraDataEditableFieldsMixin(BaseModel):
    minions: list[ExtraDataForMinion] = Field(title='Minions data', default_factory=list)


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


# REST


class ExtraDataListItemSchema(BaseModel):
    source: str = Field(title='Source', alias='_source', exclude=True)
    name: str = Field(title='Name', alias='_name', exclude=True)

    model_config = ConfigDict(
        extra='allow',
    )
