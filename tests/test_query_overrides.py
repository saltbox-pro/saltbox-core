import re
from typing import Any, ClassVar

import pytest

from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, MultilanguageFieldRepositoryMixin
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from tests.fixtures.mongo_repository_fixtures import SampleModel

OBJECT_ID_HEX = '65f1a2b3c4d5e6f7890a1b2c'

TITLE_OR = {'$or': [{'template.title': 'ping'}, {'template.title.ru': 'ping'}, {'template.title.en': 'ping'}]}


class MultilanguageSampleRepository(BaseMongoRepository[SampleModel], MultilanguageFieldRepositoryMixin):
    class Meta:
        collection_name = 'test_collection'
        auto_now_add_fields = ['created']
        auto_now_fields = ['modified']
        query_overrides: ClassVar[dict[re.Pattern, str]] = {
            re.compile(r'^template\.title$'): 'multilanguage_field_query_override',
            re.compile(r'^template\.description$'): 'multilanguage_field_query_override',
            re.compile(r'^extra_a$'): 'id_in_query_override',
            re.compile(r'^extra_b$'): 'id_in_query_override',
        }

    async def id_in_query_override(
        self, field_name: str, field_match: re.Match, field_value: Any, full_raw_query: dict
    ) -> dict[str, Any]:
        return {'_id': {'$in': [field_value]}}


@pytest.mark.asyncio
async def test_single_override_field(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'template.title': 'ping'})

    assert result == TITLE_OR


@pytest.mark.asyncio
async def test_two_override_fields_merged_with_and(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'template.title': 'ping', 'template.description': 'desc'})

    assert result == {
        '$and': [
            TITLE_OR,
            {
                '$or': [
                    {'template.description': 'desc'},
                    {'template.description.ru': 'desc'},
                    {'template.description.en': 'desc'},
                ]
            },
        ]
    }


@pytest.mark.asyncio
async def test_override_with_objectid_scalar_field(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'template.title': 'ping', 'name': OBJECT_ID_HEX})

    assert result == {
        '$and': [
            TITLE_OR,
            {'$or': [{'name': OBJECT_ID_HEX}, {'name': PyObjectId(OBJECT_ID_HEX)}]},
        ]
    }


@pytest.mark.asyncio
async def test_objectid_scalar_field_alone_stays_top_level(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'name': OBJECT_ID_HEX})

    assert result == {'$or': [{'name': OBJECT_ID_HEX}, {'name': PyObjectId(OBJECT_ID_HEX)}]}


@pytest.mark.asyncio
async def test_override_inside_and_list(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'$and': [{'name': 'plain'}, {'template.title': 'ping'}]})

    assert result == {'$and': [{'name': 'plain'}, TITLE_OR]}


@pytest.mark.asyncio
async def test_plain_scalar_field_unchanged(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'name': 'just a string'})

    assert result == {'name': 'just a string'}


@pytest.mark.asyncio
async def test_overrides_with_same_non_operator_key_merged_with_and(mocked_db):
    repo = MultilanguageSampleRepository(mocked_db)

    result = await repo.__prepare_query__({'extra_a': 'a', 'extra_b': 'b'})

    assert result == {'$and': [{'_id': {'$in': ['a']}}, {'_id': {'$in': ['b']}}]}
