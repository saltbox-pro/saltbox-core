from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import (
    BaseTreeModel,
    IDMixin,
    MongoQuery,
    MongoQueryField,
    PyObjectId,
    QueryParams,
    SortParams,
    TreeMixin,
)
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin, SkipLimitParams


class CollectionComputedFieldsMixin(BaseModel):
    full_query: MongoQuery = MongoQueryField


class CollectionReadOnlyFieldsMixin(BaseModel):
    slug: str | None = Field(default=None, title='Slug')
    owner_id: str | None = Field(title='Owner', min_length=3, max_length=50, default=None)
    parent_title: str | None = Field(title='Parent Title', default=None)


class CollectionEditableFieldsMixin(BaseModel):
    title: str = Field(title='Title', min_length=3, max_length=50)
    description: str = Field(title='Description', default='', max_length=500)
    query: MongoQuery = MongoQueryField
    order: int = Field(title='Order', ge=0, default=0)
    parent_slug: str | None = Field(
        title='Parent Slug', default=None, description='Slug of the parent collection, if any'
    )


class CollectionCreateSchema(CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin, TreeMixin):
    pass


class CollectionUpdateSchema(CollectionEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class CollectionModel(
    BaseTreeModel,
    CreatedModifiedMixin,
    CollectionEditableFieldsMixin,
    CollectionReadOnlyFieldsMixin,
    CollectionComputedFieldsMixin,
): ...


# System


class CollectionMoveSchema(IDMixin, TreeMixin):
    order: int = Field(title='Order', ge=0, default=0)


# REST


class CollectionCreateRequestSchema(CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin): ...


class CollectionUpdateRequestSchema(BaseModel):
    title: str = Field(title='Title', min_length=3, max_length=50)
    description: str = Field(title='Description', default='', max_length=500)
    query: MongoQuery = MongoQueryField


class CollectionMoveRequestSchema(BaseModel):
    target_id: PyObjectId
    parent_id: PyObjectId
    insert_before_id: PyObjectId | None = None


class CollectionDetailSchema(CollectionModel): ...


class CollectionBaseTreeModel(BaseTreeModel):
    query: MongoQuery = MongoQueryField
    full_query: MongoQuery = MongoQueryField
    slug: str
    title: str


class CollectionTreeNodeSchema(IDMixin):
    title: str = Field(title='Title', min_length=3, max_length=50)
    description: str = Field(title='Description', default='', max_length=500)
    slug: str = Field(title='Slug')

    parent_id: PyObjectId | None = Field(title='Parent ID', default=None)
    children: list['CollectionTreeNodeSchema'] = Field(title='Children', default_factory=list)


class CollectionListBody(SkipLimitParams, QueryParams, SortParams):
    model_config = ConfigDict(extra='ignore')


# Permissions


class CollectionActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'
    LIST = 'list'
