from datetime import datetime

import pytest

from saltbox_core.minion_collections.repositories.collection_repository import (
    CollectionRepository,
    get_collection_repository,
)
from saltbox_core.minion_collections.schemas.collection_schemas import CollectionCreateSchema, CollectionModel
from saltbox_sdk.db.exceptions import DuplicateKeyError
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.mark.asyncio
async def test_repository_initialization(mocked_db):
    """Test for repository initialization"""
    repo = CollectionRepository(mocked_db)

    # Check that the collection is obtained correctly
    assert repo.Meta.collection_name == 'minion_collections'
    assert repo.Meta.auto_now_add_fields == ['created']
    assert repo.Meta.auto_now_fields == ['modified']
    assert repo.default_model == CollectionModel


@pytest.mark.asyncio
async def test_collection_repository_create(mocked_db):
    """Test for creating a collection through repository"""
    # Create repository instance with mocked database
    repo = CollectionRepository(mocked_db)

    root_collection = CollectionCreateSchema(title='Root collection', slug='root', query={})
    await repo.create(root_collection)

    root_collection = await repo.get(query={'slug': 'root'})

    # Prepare test data
    collection_data = CollectionCreateSchema(
        title='Тестовая коллекция', slug='test-collection', query={'grains.os': 'Ubuntu'}, parent_id=root_collection.id
    )

    # Call create method
    created_collection = await repo.create(collection_data)

    # Check results
    assert isinstance(created_collection, CollectionModel)
    assert created_collection.title == 'Тестовая коллекция'
    assert created_collection.slug == 'test-collection'
    assert created_collection.query == {'grains.os': 'Ubuntu'}
    assert isinstance(created_collection.id, PyObjectId)
    assert isinstance(created_collection.created, datetime)
    assert isinstance(created_collection.modified, datetime)


@pytest.mark.asyncio
async def test_collection_repository_create_with_dict(mocked_db):
    """Test for creating a collection through repository using a dictionary"""
    repo = CollectionRepository(mocked_db)

    # Use dictionary instead of schema
    collection_data = {
        'title': 'Тестовая коллекция 2',
        'slug': 'test-collection-2',
        'query': {'grains.cpu_model': {'$regex': 'Intel'}},
    }

    created_collection = await repo.create(collection_data)

    assert isinstance(created_collection, CollectionModel)
    assert created_collection.title == 'Тестовая коллекция 2'
    assert created_collection.slug == 'test-collection-2'
    assert created_collection.query == {'grains.cpu_model': {'$regex': 'Intel'}}
    assert isinstance(created_collection.created, datetime)
    assert isinstance(created_collection.modified, datetime)


@pytest.mark.asyncio
async def test_collection_repository_create_duplicate(mocked_db):
    """Test for creating a collection with a duplicate slug"""
    repo = CollectionRepository(mocked_db)

    # Create first collection
    await repo.create({'title': 'Первая коллекция', 'slug': 'duplicate-slug', 'query': {'grains.os': 'Ubuntu'}})

    # Try to create second collection with the same slug
    duplicate_data = {'title': 'Вторая коллекция', 'slug': 'duplicate-slug', 'query': {'grains.os': 'CentOS'}}

    # Check that exception will be raised
    with pytest.raises(DuplicateKeyError):
        await repo.create(duplicate_data)


@pytest.mark.asyncio
async def test_get_collection_repository(mocked_db):
    """Test for get_collection_repository function"""
    # Call the function with mocked database
    repo = get_collection_repository(mocked_db)

    # Check that it returns a CollectionRepository instance
    assert isinstance(repo, CollectionRepository)
