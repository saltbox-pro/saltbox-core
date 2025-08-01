from datetime import datetime

import pytest

from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import (
    MultipleObjectsFoundException,
    ObjectNotFoundException,
    ObjectUpdateException,
)
from tests.fixtures.mongo_repository_fixtures import (
    CreateUpdateModel,
    SampleModel,
    SampleModelProjection,
    SampleRepository,
    SampleRepositoryWithBadCreatedField,
    SampleRepositoryWithBadModifiedField,
    SampleRepositoryWithNoIdModel,
    SampleRepositoryWithoutCollectionName,
)


@pytest.mark.asyncio
async def test_repository_initialization(mocked_db):
    """Test repository initialization"""
    repo = SampleRepository(mocked_db)

    assert repo.Meta.collection_name == 'test_collection'
    assert repo.Meta.auto_now_add_fields == ['created']
    assert repo.Meta.auto_now_fields == ['modified']
    assert repo.default_model == SampleModel


@pytest.mark.asyncio
async def test_repository_initialization_with_model_without_id(mocked_db):
    """Test repository initialization"""
    with pytest.raises(Exception, match='Document class should have `id` field'):
        SampleRepositoryWithNoIdModel(mocked_db)


@pytest.mark.asyncio
async def test_repository_initialization_without_collection_name(mocked_db):
    """Test repository initialization"""
    with pytest.raises(Exception, match='Meta should contain `collection_name`'):
        SampleRepositoryWithoutCollectionName(mocked_db)


@pytest.mark.asyncio
async def test_repository_initialization_with_bad_created_field(mocked_db):
    """Test repository initialization"""
    with pytest.raises(Exception, match='Meta `auto_now_add_fields` `bad_created` should be in model fields'):
        SampleRepositoryWithBadCreatedField(mocked_db)


@pytest.mark.asyncio
async def test_repository_initialization_with_bad_modified_field(mocked_db):
    """Test repository initialization"""
    with pytest.raises(Exception, match='Meta `auto_now_fields` `bad_modified` should be in model fields'):
        SampleRepositoryWithBadModifiedField(mocked_db)


@pytest.mark.asyncio
async def test_create_and_get(mocked_db):
    """Test object creation and retrieval"""
    repo = SampleRepository(mocked_db)

    # Create a new object
    data = CreateUpdateModel(name='Test Object', description='Test Description')
    created_obj = await repo.create(data)

    # Check that the object is created correctly
    assert isinstance(created_obj, SampleModel)
    assert created_obj.name == 'Test Object'
    assert created_obj.description == 'Test Description'
    assert isinstance(created_obj.id, PyObjectId)
    assert isinstance(created_obj.created, datetime)
    assert isinstance(created_obj.modified, datetime)

    # Get object by id
    retrieved_obj = await repo.get(created_obj.id)
    assert retrieved_obj.id == created_obj.id
    assert retrieved_obj.name == created_obj.name
    assert retrieved_obj.description == created_obj.description


@pytest.mark.asyncio
async def test_create_with_dict(mocked_db):
    """Test object creation using a dictionary"""
    repo = SampleRepository(mocked_db)

    # Create a new object using dictionary
    data = {'name': 'Dict Object', 'description': 'Created from dict'}
    created_obj = await repo.create(data)

    assert created_obj.name == 'Dict Object'
    assert created_obj.description == 'Created from dict'


@pytest.mark.asyncio
async def test_get_with_projection(mocked_db):
    """Test object retrieval with projection"""
    repo = SampleRepository(mocked_db)

    # Create an object
    data = {'name': 'Projection Test', 'description': 'Testing projection'}
    created_obj = await repo.create(data)

    # Get object with projection
    projected_obj = await repo.get(created_obj.id, projection_model=SampleModelProjection)

    assert isinstance(projected_obj, SampleModelProjection)
    assert projected_obj.name == 'Projection Test'
    assert not hasattr(projected_obj, 'description')


@pytest.mark.asyncio
async def test_get_by_query(mocked_db):
    """Test object retrieval by query"""
    repo = SampleRepository(mocked_db)

    # Create objects
    await repo.create({'name': 'Query Test 1', 'description': 'First object'})
    await repo.create({'name': 'Query Test 2', 'description': 'Second object'})

    # Get object by query
    obj = await repo.get({'name': 'Query Test 1'})

    assert obj.name == 'Query Test 1'
    assert obj.description == 'First object'


@pytest.mark.asyncio
async def test_object_not_found(mocked_db):
    """Test situation when object is not found"""
    repo = SampleRepository(mocked_db)

    # Try to get a non-existent object
    with pytest.raises(ObjectNotFoundException):
        await repo.get(PyObjectId('000000000000000000000000'))

    # Try to get by non-existent query
    with pytest.raises(ObjectNotFoundException):
        await repo.get({'name': 'Non-existent Object'})


@pytest.mark.asyncio
async def test_multiple_objects_found(mocked_db):
    """Test situation when multiple objects are found"""
    repo = SampleRepository(mocked_db)

    # Create multiple objects with the same description
    await repo.create({'name': 'Multiple 1', 'description': 'Same description'})
    await repo.create({'name': 'Multiple 2', 'description': 'Same description'})

    # Try to get object by description - should return multiple results
    with pytest.raises(MultipleObjectsFoundException):
        await repo.get({'description': 'Same description'})


@pytest.mark.asyncio
async def test_update(mocked_db):
    """Test object update"""
    repo = SampleRepository(mocked_db)

    # Create object
    created_obj = await repo.create({'name': 'Update Test', 'description': 'Before update'})

    # Update object
    updated_obj = await repo.update(created_obj.id, {'name': 'Updated Name', 'description': 'After update'})

    assert updated_obj.id == created_obj.id
    assert updated_obj.name == 'Updated Name'
    assert updated_obj.description == 'After update'
    assert updated_obj.created == created_obj.created
    assert updated_obj.modified > created_obj.modified

    # Check that the data was actually updated in the DB
    retrieved_obj = await repo.get(created_obj.id)
    assert retrieved_obj.name == 'Updated Name'
    assert retrieved_obj.description == 'After update'


@pytest.mark.asyncio
async def test_update_with_model(mocked_db):
    """Test object update using a model"""
    repo = SampleRepository(mocked_db)

    # Create object
    created_obj = await repo.create({'name': 'Model Update Test', 'description': 'Before model update'})

    # Update using model
    update_data = CreateUpdateModel(name='Model Updated', description='After model update')
    updated_obj = await repo.update(created_obj.id, update_data)

    assert updated_obj.name == 'Model Updated'
    assert updated_obj.description == 'After model update'


@pytest.mark.asyncio
async def test_update_with_projection(mocked_db):
    """Test object update with result projection"""
    repo = SampleRepository(mocked_db)

    # Create object
    created_obj = await repo.create({'name': 'Projection Update Test', 'description': 'Testing projection in update'})

    # Update object and get projection
    projected_obj = await repo.update(
        created_obj.id, {'name': 'Updated With Projection'}, projection_model=SampleModelProjection
    )

    assert isinstance(projected_obj, SampleModelProjection)
    assert projected_obj.name == 'Updated With Projection'
    assert not hasattr(projected_obj, 'description')


@pytest.mark.asyncio
async def test_update_not_found(mocked_db):
    """Test update of a non-existent object"""
    repo = SampleRepository(mocked_db)

    # Try to update a non-existent object
    with pytest.raises(ObjectUpdateException):
        await repo.update(
            PyObjectId('000000000000000000000000'), {'name': "Won't Update", 'description': "Object doesn't exist"}
        )


@pytest.mark.asyncio
async def test_delete(mocked_db):
    """Test object deletion"""
    repo = SampleRepository(mocked_db)

    # Create object
    created_obj = await repo.create({'name': 'Delete Test', 'description': 'To be deleted'})

    # Delete object
    deleted_count = await repo.delete(created_obj.id)
    assert deleted_count == 1

    # Check that the object was actually deleted
    with pytest.raises(ObjectNotFoundException):
        await repo.get(created_obj.id)


@pytest.mark.asyncio
async def test_delete_not_found(mocked_db):
    """Test deletion of a non-existent object"""
    repo = SampleRepository(mocked_db)

    # Try to delete a non-existent object
    with pytest.raises(ObjectNotFoundException):
        await repo.delete(PyObjectId('000000000000000000000000'))


@pytest.mark.asyncio
async def test_delete_many(mocked_db):
    """Test bulk deletion of objects"""
    repo = SampleRepository(mocked_db)

    # Create multiple objects
    await repo.create({'name': 'Batch Delete 1', 'description': 'To be batch deleted'})
    await repo.create({'name': 'Batch Delete 2', 'description': 'To be batch deleted'})
    await repo.create({'name': 'Batch Delete 3', 'description': 'To be batch deleted'})
    await repo.create({'name': 'Keep Me', 'description': 'Should not be deleted'})

    # Delete objects by query
    deleted_count = await repo.delete_many({'description': 'To be batch deleted'})
    assert deleted_count == 3

    # Check that only one object remains
    assert await repo.count() == 1
    remaining = await repo.get({'name': 'Keep Me'})
    assert remaining.name == 'Keep Me'


@pytest.mark.asyncio
async def test_get_list(mocked_db):
    """Test retrieving a list of objects"""
    repo = SampleRepository(mocked_db)

    # Create multiple objects
    await repo.create({'name': 'List Test 1', 'description': 'First for list'})
    await repo.create({'name': 'List Test 2', 'description': 'Second for list'})
    await repo.create({'name': 'List Test 3', 'description': 'Third for list'})
    await repo.create({'name': 'Other', 'description': 'Not for list'})

    # Get a list of objects by query
    items = await repo.get_list({'name': {'$regex': 'List Test'}})
    assert len(items) == 3

    # Check sorting and pagination
    items = await repo.get_list({'name': {'$regex': 'List Test'}}, limit=2)
    assert len(items) == 2

    # Check skip
    items = await repo.get_list({'name': {'$regex': 'List Test'}}, skip=1)
    assert len(items) == 2
    assert items[0].name != 'List Test 1'

    # Check skip and limit
    items = await repo.get_list({'name': {'$regex': 'List Test'}}, limit=1, skip=1)
    assert len(items) == 1
    assert items[0].name == 'List Test 2'


@pytest.mark.asyncio
async def test_get_list_with_projection(mocked_db):
    """Test retrieving a list of objects with projection"""
    repo = SampleRepository(mocked_db)

    # Create objects
    await repo.create({'name': 'Projection List 1', 'description': 'For projection list'})
    await repo.create({'name': 'Projection List 2', 'description': 'For projection list'})

    # Get list with projection
    items = await repo.get_list({'name': {'$regex': 'Projection List'}}, projection_model=SampleModelProjection)

    assert len(items) == 2
    assert isinstance(items[0], SampleModelProjection)
    assert items[0].name.startswith('Projection List')
    assert not hasattr(items[0], 'description')


@pytest.mark.asyncio
async def test_count_and_exists(mocked_db):
    """Test count and exists methods"""
    repo = SampleRepository(mocked_db)

    # Create objects
    await repo.create({'name': 'Count Test 1', 'description': 'For counting'})
    await repo.create({'name': 'Count Test 2', 'description': 'For counting'})
    await repo.create({'name': 'Other Count', 'description': 'Not for counting'})

    # Check count
    count = await repo.count({'description': 'For counting'})
    assert count == 2

    # Check exists
    assert await repo.exists({'name': 'Count Test 1'}) == True
    assert await repo.exists({'name': 'Non-Existent'}) == False
