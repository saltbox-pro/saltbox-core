from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from saltbox_sdk.db.mongo.schemas_base import IDMixin, PyObjectId
from saltbox_sdk.utilities.helpers import utc_now


class CollectionMembershipRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: Literal['started', 'succeeded', 'failed', 'skipped'] = 'started'
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class CollectionSynchronizationModel(IDMixin):
    slug: str
    parent_id: PyObjectId | None = None
    query: dict[str, Any] = Field(default_factory=dict)


class CollectionSynchronizationBranch(BaseModel):
    collection_id: str
    children: list['CollectionSynchronizationBranch'] = Field(default_factory=list)
