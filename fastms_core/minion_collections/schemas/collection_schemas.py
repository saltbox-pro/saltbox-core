from pydantic import BaseModel, ConfigDict, Field

from fastms_core.db.mongo.schemas_base import (
    CreatedModifiedMixin,
    IDMixin,
    MongoQuery,
)


class CollectionReadOnlyFieldsMixin:
    slug: str = Field(title='Slug', pattern=r'^[a-z0-9-]+$', min_length=3, max_length=30)
    query: MongoQuery = Field(
        default_factory=dict,
        title='MongoDB Query',
        description='A valid MongoDB query dictionary',
        examples=[
            {'grains.os': 'Ubuntu'},
            {'grains.cpu_model': {'$regex': 'Intel'}},
        ],
        json_schema_extra={'example': {'grains.cpu_model': {'$not': {'$regex': 'Intel'}}}},
    )


class CollectionEditableFieldsMixin:
    title: str = Field(title='Title', min_length=3, max_length=50)


class CollectionCreateSchema(BaseModel, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin):
    pass


class CollectionUpdateSchema(BaseModel, CollectionEditableFieldsMixin):
    model_config = ConfigDict(
        extra='forbid',
    )


class CollectionModel(
    BaseModel, CreatedModifiedMixin, CollectionEditableFieldsMixin, CollectionReadOnlyFieldsMixin, IDMixin
):
    pass


class CollectionDetailSchema(CollectionModel):
    allowed_actions: list[str] = Field(title='Allowed actions')


# HINT: We can't create optional but not nullable field - https://github.com/pydantic/pydantic/issues/8394
# Waiting for Pydantic 2.11 release
# class CollectionPartialUpdate(BaseModel):
#     title: str | None = None
#     slug: str | None = None
#     has_boobs: bool | None = None

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
