from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from salt_box_core.db.mongo.schemas_base import BaseTreeModel, MongoQuery, TreeMixin
from salt_box_core.db.schemas_base import CreatedModifiedMixin

MongoQueryField: dict[str, Any] = Field(
    default_factory=dict,
    title='MongoDB Query',
    description='A valid MongoDB query dictionary',
    examples=[
        {'grains.os': 'Ubuntu'},
        {'grains.cpu_model': {'$regex': 'Intel'}},
    ],
    json_schema_extra={'example': {'grains.cpu_model': {'$not': {'$regex': 'Intel'}}}},
)


class CollectionComputedFieldsMixin:
    full_query: MongoQuery = MongoQueryField


class CollectionReadOnlyFieldsMixin:
    slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)
    parent_title: str | None = Field(title='Title', min_length=3, max_length=50, default=None)


class CollectionEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3, max_length=50)
    query: MongoQuery = MongoQueryField
    parent_slug: str | None = Field(
        title='Parent Slug',
        pattern=r'^[a-z0-9-]+$',
        min_length=3,
        max_length=30,
        default=None,
        description='Slug of the parent collection, if any',
    )


class CollectionCreateSchema(BaseModel, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin, TreeMixin):
    pass


class CollectionCreateRequestSchema(BaseModel, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin):
    parent_slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)


class CollectionUpdateSchema(BaseModel, CollectionEditableFieldsMixin, TreeMixin):
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
    pass


class CollectionDetailSchema(CollectionModel):
    allowed_actions: list[str] = Field(title='Allowed actions')


class CollectionBaseTreeModel(BaseTreeModel):
    query: MongoQuery = MongoQueryField
    full_query: MongoQuery = MongoQueryField
    slug: str
    title: str


# HINT: We can't create optional but not nullable field - https://github.com/pydantic/pydantic/issues/8394
# Waiting for Pydantic 2.11 release
# class CollectionPartialUpdate(BaseModel):
#     title: str | None = None
#     slug: str | None = None

#     model_config = ConfigDict(
#         extra='forbid',
#     )


# CollectionUpdate = create_model(  # type: ignore[call-overload]
#     'CollectionUpdate',
#     **{
#         name: (field_info.annotation, field_info)
#         for name, field_info in CollectionBase.model_fields.items()
#         if field_info.json_schema_extra and not field_info.json_schema_extra.get('readOnly', False)
#     },
#     __base__=BaseModel,
# )
