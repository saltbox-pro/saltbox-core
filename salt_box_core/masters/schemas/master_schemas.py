from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class MasterStatus(str, Enum):
    new = 'new'
    accepted = 'accepted'
    rejected = 'rejected'


class MasterReadOnlyFieldsMixin:
    name: str = Field(title='Name', min_length=3)


class MasterSecretsMixin:
    secret: str | None = Field(title='Secret', default=None)  # TODO @: make encrypted


class MasterEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3)

    status: MasterStatus = Field(title='Status', default=MasterStatus.new)
    alias: str | None = Field(title='Alias', default=None)


class MasterCreateSchema(BaseModel, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, MasterSecretsMixin):
    pass


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin, MasterSecretsMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class MasterModel(
    BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, MasterSecretsMixin, IDMixin
):
    pass


class MasterViewSchema(BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, IDMixin):
    pass


class MasterQueryParams(SkipLimitParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='forbid')
