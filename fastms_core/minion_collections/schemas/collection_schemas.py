from pydantic import ConfigDict, Field

from fastms_core.db.mongo.schemas_base import MongoQueryBaseSchema, PaginatedListParams, PaginatedResponse, PyObjectId
from fastms_core.minion_collections.schemas.minion_schemas import MinionListSchema


class MinionCollectionSchema(MongoQueryBaseSchema):
    id: PyObjectId | None = Field(alias='_id', default=None)
    title: str = Field(...)
    slug: str = Field(..., pattern=r'^[a-z0-9-]+$')

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class MinionCollectionCreateSchema(MinionCollectionSchema):
    pass


class MinionCollectionUpdateSchema(MinionCollectionSchema):
    pass


class MinionCollectionListSchema(MinionCollectionSchema):
    pass


class MinionCollectionAuthzSchema(MinionCollectionSchema):
    allowed_actions: list[str]


class MinionCollectionDetailSchema(MinionCollectionAuthzSchema):
    minions: PaginatedResponse[MinionListSchema]


class MinionCollectionDetailBody(PaginatedListParams, MongoQueryBaseSchema):
    model_config = ConfigDict(
        extra='forbid',
    )
