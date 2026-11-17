import re
from types import SimpleNamespace

import pytest
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from saltbox_core.task_templates.services import source, template
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService
from saltbox_sdk.db.mongo import transaction
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['commit', 'retry', 'rollback', 'empty'])
async def test_delete_source_defers_cleanup_until_commit(outcome, tmp_path, mocker):
    repos_dir = tmp_path / 'repos'
    local_dir = repos_dir / 'source'
    serve_dir = tmp_path / 'serve'
    local_dir.mkdir(parents=True)
    serve_dir.mkdir()
    for module in (source, template):
        mocker.patch.object(
            module,
            'SETTINGS',
            SimpleNamespace(local_repos_dir=repos_dir, salt_modules_serve_dir=serve_dir),
        )

    files = [folder / name for folder in (local_dir, serve_dir) for name in ('template.sls', 'extra.sls')]
    for file in files:
        file.touch()

    source_record = SimpleNamespace(id=PyObjectId(), local_path='source', root='.')
    templates = (
        [
            SimpleNamespace(id=PyObjectId(), local_path='source', sls_rel_path='template.sls', schema_rel_path=None),
            SimpleNamespace(id=PyObjectId(), local_path='source', sls_rel_path=None, schema_rel_path=None),
        ]
        if outcome != 'empty'
        else []
    )
    sshfs_file = mocker.sentinel.sshfs_file
    sshfs_sync = SimpleNamespace(remove=mocker.AsyncMock())
    source_repo = SimpleNamespace(get=mocker.AsyncMock(return_value=source_record), delete=mocker.AsyncMock())
    template_repo = SimpleNamespace(get_list=mocker.AsyncMock(return_value=templates), delete_many=mocker.AsyncMock())
    pillar_repo = SimpleNamespace(delete_many=mocker.AsyncMock())
    sshfs_repo = SimpleNamespace(get_list=mocker.AsyncMock(return_value=[sshfs_file]), delete_many=mocker.AsyncMock())
    template_service = template.TaskTemplateService(template_repo, pillar_repo)
    remove_template_files = mocker.spy(template_service, '_remove_files')
    service = source.TemplateSourceService(
        repo=source_repo,
        template_service=template_service,
        file_service=SshfsFileService(sshfs_repo, sshfs_sync),
        task_service=mocker.sentinel.task_service,
    )

    async def delete_source(**kwargs):
        assert all(file.exists() for file in files)
        sshfs_sync.remove.assert_not_awaited()
        if outcome == 'rollback':
            raise RuntimeError('failed to delete source')
        if outcome == 'retry' and source_repo.delete.await_count == 1:
            raise OperationFailure('retry', details={'errorLabels': ['TransientTransactionError']})
        return 1

    source_repo.delete.side_effect = delete_source
    original_commit = AsyncClientSession.commit_transaction

    async def commit(session):
        assert all(file.exists() for file in files)
        sshfs_sync.remove.assert_not_awaited()
        remove_template_files.assert_not_awaited()
        await original_commit(session)

    mocker.patch.object(AsyncClientSession, 'commit_transaction', commit)
    async with AsyncMongoClient(connect=False) as client:
        mocker.patch.object(transaction, '_get_mongo_client', return_value=client)
        if outcome == 'rollback':
            with pytest.raises(RuntimeError, match='failed to delete source'):
                await service.delete(source_record.id)
            assert all(file.exists() for file in files)
            sshfs_sync.remove.assert_not_awaited()
            remove_template_files.assert_not_awaited()
        else:
            assert await service.delete(source_record.id) == 1
            assert not local_dir.exists()
            assert not any(file.exists() for file in files)
            sshfs_sync.remove.assert_awaited_once_with(sshfs_file)
            assert [call.args[0] for call in remove_template_files.await_args_list] == templates

    expected_attempts = 2 if outcome == 'retry' else 1
    session = source_repo.get.await_args.kwargs['session']
    assert session.has_ended
    for operation in (
        source_repo.get,
        source_repo.delete,
        template_repo.get_list,
        template_repo.delete_many,
        sshfs_repo.get_list,
        sshfs_repo.delete_many,
    ):
        assert operation.await_count == expected_attempts
        assert all(call.kwargs['session'] is session for call in operation.await_args_list)

    if templates:
        assert pillar_repo.delete_many.await_count == expected_attempts
        call = pillar_repo.delete_many.await_args
        assert call.kwargs['session'] is session
        pattern = call.kwargs['query']['pillarenv']['$regex']
        assert all(re.match(pattern, f'task_tpl:{tpl.id};user:test') for tpl in templates)
        assert not re.match(pattern, f'task_tpl:{PyObjectId()};user:{templates[1].id}')
    else:
        pillar_repo.delete_many.assert_not_awaited()
