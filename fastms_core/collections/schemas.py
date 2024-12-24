from typing import ClassVar

from beanie import PydanticObjectId
from pydantic import ConfigDict, Field

from fastms_core.db.mongo.schemas_base import MongoQueryBaseSchema, PaginatedListParams


class MinionCollectionBaseSchema(MongoQueryBaseSchema):
    title: str = Field(title='Title')


class MinionCollectionDBSchema(MinionCollectionBaseSchema):
    id: PydanticObjectId = Field(title='ID', alias='_id', serialization_alias='id')


class MinionCollectionSchema(MinionCollectionDBSchema):
    pass


class MinionCollectionCreateSchema(MinionCollectionBaseSchema):
    pass


class MinionCollectionUpdateSchema(MinionCollectionBaseSchema):
    pass


class MinionCollectionListSchema(MinionCollectionDBSchema):
    pass


class MinionCollectionListQueryParams(PaginatedListParams):
    model_config: ClassVar[ConfigDict] = {'extra': 'forbid'}
