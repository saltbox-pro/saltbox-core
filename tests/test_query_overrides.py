import re
from typing import Any, ClassVar

import pytest

from saltbox_sdk.db.mongo.repository_base import BaseMongoRepository, MultilanguageFieldRepositoryMixin
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from tests.fixtures.mongo_repository_fixtures import SampleModel

OBJECT_ID_HEX = '65f1a2b3c4d5e6f7890a1b2c'
RU_TITLE = 'Обновление системы'
EN_TITLE = 'System update'
RU_DESCRIPTION = 'Установка обновлений безопасности'


def make_multilanguage_query(field_name: str, field_value: Any, group_operator: str = '$or') -> dict[str, Any]:
    return {
        group_operator: [
            {field_name: field_value},
            {f'{field_name}.ru': field_value},
            {f'{field_name}.en': field_value},
        ]
    }


TITLE_OR = make_multilanguage_query('template.title', RU_TITLE)
DESCRIPTION_OR = make_multilanguage_query('template.description', RU_DESCRIPTION)

POSITIVE_OPERATOR_VALUES = [
    pytest.param(RU_TITLE, id='='),
    pytest.param({'$eq': RU_TITLE}, id='explicit-eq'),
    pytest.param({'$lt': RU_TITLE}, id='<'),
    pytest.param({'$gt': RU_TITLE}, id='>'),
    pytest.param({'$lte': RU_TITLE}, id='<='),
    pytest.param({'$gte': RU_TITLE}, id='>='),
    pytest.param({'$regex': 'Обновление', '$options': 'i'}, id='contains'),
    pytest.param({'$regex': '^Обновление', '$options': 'i'}, id='beginsWith'),
    pytest.param({'$regex': 'системы$', '$options': 'i'}, id='endsWith'),
    pytest.param(None, id='null'),
    pytest.param({'$in': [RU_TITLE, EN_TITLE]}, id='in'),
    pytest.param({'$gte': EN_TITLE, '$lte': RU_TITLE}, id='between'),
]
NEGATIVE_OPERATOR_VALUES = [
    pytest.param({'$ne': RU_TITLE}, id='!='),
    pytest.param({'$not': {'$regex': 'Обновление', '$options': 'i'}}, id='doesNotContain'),
    pytest.param({'$not': {'$regex': '^Обновление', '$options': 'i'}}, id='doesNotBeginWith'),
    pytest.param({'$not': {'$regex': 'системы$', '$options': 'i'}}, id='doesNotEndWith'),
    pytest.param({'$ne': None}, id='notNull'),
    pytest.param({'$nin': [RU_TITLE, EN_TITLE]}, id='notIn'),
    pytest.param({'$not': {'$gte': EN_TITLE, '$lte': RU_TITLE}}, id='notBetween'),
]
MULTILANGUAGE_DOCUMENTS = [
    {'_id': 'legacy_ru', 'template': {'title': RU_TITLE}},
    {'_id': 'legacy_en', 'template': {'title': EN_TITLE}},
    {'_id': 'localized_update', 'template': {'title': {'ru': RU_TITLE, 'en': EN_TITLE}}},
    {
        '_id': 'localized_cleanup',
        'template': {'title': {'ru': 'Очистка временных файлов', 'en': 'Clean temporary files'}},
    },
    {'_id': 'localized_restart', 'template': {'title': {'ru': 'Перезапуск службы', 'en': 'Restart service'}}},
    {'_id': 'without_title', 'template': {}},
]


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


@pytest.fixture
def repo(mocked_db):
    return MultilanguageSampleRepository(mocked_db)


@pytest.fixture
def multilingual_repo(repo):
    repo.collection.collection.insert_many(MULTILANGUAGE_DOCUMENTS)
    return repo


async def find_matching_ids(repo, field_value):
    query = await repo.__prepare_query__({'template.title': field_value})
    return sorted(doc['_id'] for doc in repo.collection.collection.find(query))


@pytest.mark.asyncio
@pytest.mark.parametrize('field_value', POSITIVE_OPERATOR_VALUES)
async def test_positive_operators_use_or(repo, field_value):
    result = await repo.__prepare_query__({'template.title': field_value})

    assert result == make_multilanguage_query('template.title', field_value)


@pytest.mark.asyncio
@pytest.mark.parametrize('field_value', NEGATIVE_OPERATOR_VALUES)
async def test_negative_operators_use_and(repo, field_value):
    result = await repo.__prepare_query__({'template.title': field_value})

    assert result == make_multilanguage_query('template.title', field_value, '$and')


@pytest.mark.asyncio
async def test_two_override_fields_merged_with_and(repo):
    result = await repo.__prepare_query__({'template.title': RU_TITLE, 'template.description': RU_DESCRIPTION})

    assert result == {'$and': [TITLE_OR, DESCRIPTION_OR]}


@pytest.mark.asyncio
async def test_two_negative_override_fields_merged_with_and(repo):
    title_value = {'$ne': RU_TITLE}
    description_value = {'$not': {'$regex': 'безопасности', '$options': 'i'}}

    result = await repo.__prepare_query__({'template.title': title_value, 'template.description': description_value})

    assert result == {
        '$and': [
            make_multilanguage_query('template.title', title_value, '$and'),
            make_multilanguage_query('template.description', description_value, '$and'),
        ]
    }


@pytest.mark.asyncio
async def test_override_with_objectid_scalar_field(repo):
    result = await repo.__prepare_query__({'template.title': RU_TITLE, 'name': OBJECT_ID_HEX})

    assert result == {
        '$and': [
            TITLE_OR,
            {'$or': [{'name': OBJECT_ID_HEX}, {'name': PyObjectId(OBJECT_ID_HEX)}]},
        ]
    }


@pytest.mark.asyncio
async def test_objectid_scalar_field_alone_stays_top_level(repo):
    result = await repo.__prepare_query__({'name': OBJECT_ID_HEX})

    assert result == {'$or': [{'name': OBJECT_ID_HEX}, {'name': PyObjectId(OBJECT_ID_HEX)}]}


@pytest.mark.asyncio
async def test_override_inside_and_list(repo):
    result = await repo.__prepare_query__({'$and': [{'name': 'plain'}, {'template.title': RU_TITLE}]})

    assert result == {'$and': [{'name': 'plain'}, TITLE_OR]}


@pytest.mark.asyncio
async def test_negative_override_inside_or_list(repo):
    title_value = {'$ne': RU_TITLE}

    result = await repo.__prepare_query__({'$or': [{'name': 'plain'}, {'template.title': title_value}]})

    assert result == {'$or': [{'name': 'plain'}, make_multilanguage_query('template.title', title_value, '$and')]}


@pytest.mark.asyncio
async def test_plain_scalar_field_unchanged(repo):
    result = await repo.__prepare_query__({'name': 'just a string'})

    assert result == {'name': 'just a string'}


@pytest.mark.asyncio
async def test_overrides_with_same_non_operator_key_merged_with_and(repo):
    result = await repo.__prepare_query__({'extra_a': 'a', 'extra_b': 'b'})

    assert result == {'$and': [{'_id': {'$in': ['a']}}, {'_id': {'$in': ['b']}}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('field_value', 'expected_ids'),
    [
        pytest.param(RU_TITLE, ['legacy_ru', 'localized_update'], id='russian-equality'),
        pytest.param(EN_TITLE, ['legacy_en', 'localized_update'], id='english-equality'),
        pytest.param(
            {'$in': [RU_TITLE, EN_TITLE]},
            ['legacy_en', 'legacy_ru', 'localized_update'],
            id='in',
        ),
        pytest.param({'$regex': 'Обновление'}, ['legacy_ru', 'localized_update'], id='russian-contains'),
        pytest.param({'$regex': 'System'}, ['legacy_en', 'localized_update'], id='english-contains'),
    ],
)
async def test_positive_filters_match_real_multilanguage_data(multilingual_repo, field_value, expected_ids):
    assert await find_matching_ids(multilingual_repo, field_value) == expected_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('field_value', 'expected_ids'),
    [
        pytest.param(
            {'$ne': RU_TITLE},
            ['legacy_en', 'localized_cleanup', 'localized_restart', 'without_title'],
            id='russian-not-equal',
        ),
        pytest.param(
            {'$ne': EN_TITLE},
            ['legacy_ru', 'localized_cleanup', 'localized_restart', 'without_title'],
            id='english-not-equal',
        ),
        pytest.param(
            {'$nin': [RU_TITLE, EN_TITLE]},
            ['localized_cleanup', 'localized_restart', 'without_title'],
            id='not-in',
        ),
    ],
)
async def test_negative_filters_exclude_matches_in_any_language(multilingual_repo, field_value, expected_ids):
    assert await find_matching_ids(multilingual_repo, field_value) == expected_ids


@pytest.mark.asyncio
@pytest.mark.parametrize('fragment', ['Обновление', 'System'], ids=['russian', 'english'])
async def test_not_contains_excludes_matches_in_any_language(repo, fragment):
    repo.collection.collection.insert_many(MULTILANGUAGE_DOCUMENTS[2:5])

    assert await find_matching_ids(repo, {'$not': {'$regex': fragment}}) == [
        'localized_cleanup',
        'localized_restart',
    ]
