from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from salt_box_core.db.mongo.schemas_base import IDMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class MasterStatus(str, Enum):
    new = 'new'
    accepted = 'accepted'
    rejected = 'rejected'


class MasterReadOnlyFieldsMixin:
    master_id: str = Field(title='Master ID', min_length=3)


class MasterSecretsMixin:
    pubkey: str | None = Field(title='Public key', default=None)


class MasterEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3)

    status: MasterStatus = Field(title='Status', default=MasterStatus.new)


class MasterCreateSchema(BaseModel, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, MasterSecretsMixin):
    pass


class MasterUpdateSchema(BaseModel, MasterEditableFieldsMixin, MasterSecretsMixin):
    model_config = ConfigDict(
        extra='ignore',
    )


class MasterModel(
    BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, MasterSecretsMixin, IDMixin
):
    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_pubkey_set(self) -> bool:
        return self.pubkey is not None


class MasterViewSchema(BaseModel, CreatedModifiedMixin, MasterEditableFieldsMixin, MasterReadOnlyFieldsMixin, IDMixin):
    pass


class MasterQueryParams(SkipLimitParams):
    status: MasterStatus | None = Field(title='Status', default=None)

    model_config = ConfigDict(extra='forbid')
