from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams, UserShort


class PillarTgtType(StrEnum):
    ROOT = 'root'
    COLLECTION = 'collection'
    MINION = 'minion'


class ReadOnlyShortFieldsMixin:
    name: str
    value: JsonValue
    is_personal: bool = False
    is_secret: bool = False

    @model_validator(mode='after')
    def hide_secret_value(self) -> Self:
        if self.is_secret:
            self.value = '*******'
        return self


class ReadOnlyFieldsMixin(ReadOnlyShortFieldsMixin):
    tgt_type: PillarTgtType = Field(default=PillarTgtType.ROOT)
    tgt_id: PyObjectId | None = None
    pillarenv: str = Field(default='base', title='Pillar environment')
    created_by: UserShort | None = None


class EditableFieldsMixin:
    pass


class PillarCreateSchema(BaseModel, ReadOnlyFieldsMixin, EditableFieldsMixin):
    pass


class PillarUpdateSchema(BaseModel, EditableFieldsMixin):
    pass


class PillarModel(BaseModel, ReadOnlyFieldsMixin, EditableFieldsMixin, CreatedModifiedMixin, IDMixin):
    pass


class PillarListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(
        extra='ignore',
    )


class PillarTargetInfoBase(BaseModel):
    type: PillarTgtType = Field(default=PillarTgtType.ROOT)
    id: PyObjectId | None = None


class PillarTargetInfoCollection(PillarTargetInfoBase):
    title: str | None = None
    slug: str | None = None


class PillarTargetInfoMinion(PillarTargetInfoBase):
    minion_id: str | None = None
    master: str | None = None


class PillarWithTgtInfoSchema(BaseModel, ReadOnlyShortFieldsMixin, CreatedModifiedMixin, IDMixin):
    tgt_info: PillarTargetInfoCollection | PillarTargetInfoMinion


class PillarsActions(StrEnum):
    LIST = 'list'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
