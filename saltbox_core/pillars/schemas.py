from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId, QueryParams, SortParams
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams, UserShort


class PillarTgtType(StrEnum):
    ROOT = 'root'
    COLLECTION = 'collection'
    MINION = 'minion'


class ReadOnlyFieldsMixin:
    tgt_type: PillarTgtType = Field(default=PillarTgtType.ROOT)
    tgt_id: PyObjectId | None = None
    name: str
    value: JsonValue
    is_personal: bool = False
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


class PillarsActions(StrEnum):
    LIST = 'list'
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
