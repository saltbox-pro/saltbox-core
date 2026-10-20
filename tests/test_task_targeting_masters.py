import pytest

from saltbox_core.minion_collections.repositories.collection import CollectionRepository
from saltbox_core.minion_collections.repositories.extra_data import ExtraDataRepository
from saltbox_core.minion_collections.repositories.extra_data_category import ExtraDataCategoryRepository
from saltbox_core.minion_collections.repositories.minion import MinionRepository
from saltbox_core.minion_collections.services.minion import MinionService
from saltbox_core.tasks.schemas.task import TaskTargetingMastersBody, TaskTargetingMasterSchema
from saltbox_core.tasks.services.task import TaskService
from saltbox_sdk.db.mongo.schemas_base import PyObjectId, SortOrder
from saltbox_sdk.exceptions import ObjectNotFoundException, SaltBoxValidationException

GROUP_LOOKUP_PROJECT = [
    {'$group': {'_id': '$master', 'minions_count': {'$sum': 1}}},
    {'$lookup': {'from': 'master', 'localField': '_id', 'foreignField': 'master_id', 'as': 'master'}},
    {'$unwind': {'path': '$master', 'preserveNullAndEmptyArrays': True}},
    {
        '$project': {
            '_id': 0,
            'master_id': '$_id',
            'title': '$master.title',
            'status': '$master.status',
            'minions_count': 1,
        }
    },
]


@pytest.fixture
def minion_service(mocked_db, mocker):
    category_repo = ExtraDataCategoryRepository(mocked_db)
    extra_data_repo = ExtraDataRepository(mocked_db, extra_data_category_repository=category_repo)
    repo = MinionRepository(
        mocked_db, extra_data_repository=extra_data_repo, collection_repository=CollectionRepository(mocked_db)
    )
    mocker.patch.object(repo, 'aggregate', mocker.AsyncMock(return_value=[]))

    return MinionService(repo)


@pytest.fixture
def task_service(minion_service, mocker):
    return TaskService(
        repo=mocker.Mock(),
        rdb=mocker.Mock(),
        task_status_service=mocker.Mock(),
        task_template_service=mocker.Mock(get=mocker.AsyncMock()),
        task_minion_service=mocker.Mock(),
        collections_service=mocker.Mock(get_by_slug=mocker.AsyncMock(), get=mocker.AsyncMock()),
        minion_service=minion_service,
        job_service=mocker.Mock(),
    )


@pytest.mark.asyncio
async def test_pipeline_sorts_by_master_id_by_default(minion_service):
    await minion_service.get_targeting_masters(query={'master': 'm1'})

    assert minion_service.repo.aggregate.await_args.args[0] == [
        {'$match': {'master': 'm1'}},
        *GROUP_LOOKUP_PROJECT,
        {'$sort': {'master_id': 1}},
    ]


@pytest.mark.asyncio
async def test_pipeline_uses_requested_sort(minion_service):
    await minion_service.get_targeting_masters(query={}, sort={'minions_count': SortOrder.DESC})

    assert minion_service.repo.aggregate.await_args.args[0][-1] == {'$sort': {'minions_count': -1}}


@pytest.mark.asyncio
async def test_targeting_query_combines_collection_query_and_minions(task_service, mocker):
    task_service.collections_service.get_by_slug.return_value = mocker.Mock(full_query={'grains.os': 'Linux'})
    body = TaskTargetingMastersBody.model_validate(
        {
            'collection_slug': 'linux',
            'query': {'minion_id': 'a'},
            'minions': [{'minion_id': 'a', 'salt_master': 'm1'}],
        }
    )

    await task_service.get_targeting_masters(body)

    assert task_service.minion_service.repo.aggregate.await_args.args[0][0] == {
        '$match': {
            '$and': [
                {'grains.os': 'Linux'},
                {'minion_id': 'a'},
                {'$or': [{'minion_id': 'a', 'master': 'm1'}]},
            ]
        }
    }


@pytest.mark.asyncio
async def test_rows_without_known_master_are_kept(task_service, mocker):
    task_service.collections_service.get_by_slug.return_value = mocker.Mock(full_query={})
    task_service.minion_service.repo.aggregate.return_value = [
        {'master_id': 'm1', 'title': 'Master 1', 'status': 'accepted', 'minions_count': 3},
        {'master_id': None, 'minions_count': 1},
    ]

    rows = await task_service.get_targeting_masters(TaskTargetingMastersBody(collection_slug='root'))

    assert task_service.minion_service.repo.aggregate.await_args.args[0][0] == {'$match': {}}
    assert rows == [
        TaskTargetingMasterSchema(master_id='m1', title='Master 1', status='accepted', minions_count=3),
        TaskTargetingMasterSchema(master_id=None, title=None, status=None, minions_count=1),
    ]


@pytest.mark.asyncio
async def test_unknown_template_is_validation_error(task_service):
    task_service.task_template_service.get.side_effect = ObjectNotFoundException('not found')

    with pytest.raises(SaltBoxValidationException, match='Task template not found'):
        await task_service.get_targeting_masters(
            TaskTargetingMastersBody(collection_slug='root', task_template_id=PyObjectId())
        )


@pytest.mark.asyncio
async def test_unknown_collection_is_validation_error(task_service):
    task_service.collections_service.get_by_slug.side_effect = ObjectNotFoundException('not found')

    with pytest.raises(SaltBoxValidationException, match='Collection not found'):
        await task_service.get_targeting_masters(TaskTargetingMastersBody(collection_slug='missing'))


@pytest.mark.asyncio
async def test_collection_by_id(task_service, mocker):
    collection_id = PyObjectId()
    task_service.collections_service.get.return_value = mocker.Mock(full_query={'grains.os': 'Linux'})

    await task_service.get_targeting_masters(TaskTargetingMastersBody(collection_id=collection_id))

    task_service.collections_service.get.assert_awaited_once_with(query=collection_id)
    assert task_service.minion_service.repo.aggregate.await_args.args[0][0] == {
        '$match': {'$and': [{'grains.os': 'Linux'}]}
    }


def test_body_requires_collection():
    with pytest.raises(SaltBoxValidationException):
        TaskTargetingMastersBody()
