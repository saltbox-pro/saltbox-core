from datetime import datetime
from typing import Literal

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


# Statistic

StatisticsInterval = Literal['hour', 'day', 'week', 'month']


class CollectionCountPoint(BaseModel):
    timestamp: datetime = Field(description='Snapshot time in UTC')
    count: int | None = Field(description='Member count; null before recorded history or in the future')


class CollectionCountStatistics(BaseModel):
    interval: StatisticsInterval = Field(description='Calendar sampling interval')
    timezone: str = Field(description='IANA timezone used for calendar boundaries')
    history_from: datetime | None = Field(description='Earliest recorded entered_at; null if no membership records')
    points: list[CollectionCountPoint] = Field(
        description='Time-ordered snapshots of the entire collection, including period endpoints'
    )
