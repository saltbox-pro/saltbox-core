from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.utilities.helpers import Iso8601ZDatetime as TimezoneAwareDatetime


class CollectionMembershipReadOnlyFieldsMixin(BaseModel):
    collection_id: PyObjectId = Field(title='Collection ID')
    minion_inner_id: PyObjectId = Field(title='Minion internal ID')
    entered_at: TimezoneAwareDatetime = Field(title='Entered at')


class CollectionMembershipEditableFieldsMixin(BaseModel):
    exited_at: TimezoneAwareDatetime | None = Field(title='Exited at', default=None)


class CollectionMembershipCreateSchema(
    CollectionMembershipEditableFieldsMixin, CollectionMembershipReadOnlyFieldsMixin
): ...


class CollectionMembershipUpdateSchema(CollectionMembershipEditableFieldsMixin):
    model_config = ConfigDict(extra='ignore')


class CollectionMembershipModel(
    CollectionMembershipEditableFieldsMixin,
    CollectionMembershipReadOnlyFieldsMixin,
    IDMixin,
): ...
