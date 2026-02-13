from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from saltbox_sdk.db.mongo.schemas_base import BaseTreeModel, IDMixin, MongoQuery, MongoQueryField, PyObjectId, TreeMixin
from saltbox_sdk.db.schemas_base import CreatedModifiedMixin


class CollectionComputedFieldsMixin:
    full_query: MongoQuery = MongoQueryField


class CollectionReadOnlyFieldsMixin:
    slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)
    owner_id: str | None = Field(title='Owner', min_length=3, max_length=50, default=None)


class CollectionEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3, max_length=50)
    query: MongoQuery = MongoQueryField


class CollectionCreateSchema(BaseModel, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin, TreeMixin):
    pass


class CollectionCreateRequestSchema(BaseModel, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin):
    parent_slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)


class CollectionUpdateSchema(BaseModel, CollectionEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class CollectionModel(
    BaseTreeModel,
    CreatedModifiedMixin,
    CollectionEditableFieldsMixin,
    CollectionReadOnlyFieldsMixin,
    CollectionComputedFieldsMixin,
):
    parent_title: str | None = Field(title='Title', min_length=3, max_length=50, default=None)
    parent_slug: str | None = Field(
        title='Parent Slug',
        pattern=r'^[a-z0-9-]+$',
        min_length=3,
        max_length=30,
        default=None,
        description='Slug of the parent collection, if any',
    )


class CollectionDetailSchema(CollectionModel):
    allowed_actions: list[str] = Field(title='Allowed actions')


class CollectionBaseTreeModel(BaseTreeModel):
    query: MongoQuery = MongoQueryField
    full_query: MongoQuery = MongoQueryField
    slug: str
    title: str


class CollectionTreeNodeSchema(BaseModel, IDMixin):
    title: str = Field(title='Title', min_length=3, max_length=50)
    slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)

    parent_id: PyObjectId | None = Field(title='Parent ID', default=None)
    children: list['CollectionTreeNodeSchema'] = Field(title='Children', default=[])


class CollectionActions(StrEnum):
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'
    LIST = 'list'
