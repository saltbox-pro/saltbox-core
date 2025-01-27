from pydantic import ConfigDict, Field

from fastms_core.db.mongo.schemas_base import MongoQueryBaseSchema, PyObjectId


class MinionCollectionSchema(MongoQueryBaseSchema):
    id: PyObjectId | None = Field(alias='_id', default=None)
    title: str = Field(...)
    slug: str = Field(..., pattern=r'^[a-z0-9-]+$')

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            'example': {
                'id': '5f7b1b3b7b3b7b3b7b3b7b3b',
                'title': 'My collection',
                'slug': 'my_collection',
                'query': {'some_field': 'some_value'},
            }
        },
    )


class MinionCollectionCreateSchema(MinionCollectionSchema):
    pass


class MinionCollectionUpdateSchema(MinionCollectionSchema):
    pass


class MinionCollectionListSchema(MinionCollectionSchema):
    pass


class MinionCollectionSchemaWithAllowedActions(MinionCollectionSchema):
    allowed_actions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'id': '5f7b1b3b7b3b7b3b7b3b7b3b',
                'title': 'My collection',
                'slug': 'my_collection',
                'query': {'some_field': 'some_value'},
                'allowed_actions': ['retrieve', 'update', 'delete'],
            }
        }
    )
