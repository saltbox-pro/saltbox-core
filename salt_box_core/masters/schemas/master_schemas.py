from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from salt_box_core.db.mongo.schemas_base import CreatedModifiedMixin, IDMixin, SkipLimitParams


class MasterStatus(str, Enum):
    new = 'new'
    accepted = 'accepted'
    rejected = 'rejected'


class MasterReadOnlyFieldsMixin:
    name: str = Field(title='Slug')


class MasterEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3, max_length=50)

    status: MasterStatus = Field(title='Status', default=MasterStatus.new)
    alias: str | None = Field(title='Alias', default=None)


class MasterCreateSchema(BaseModel, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin):
    pass


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class MasterModel(BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, IDMixin):
    pass


class MasterQueryParams(SkipLimitParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='forbid')
