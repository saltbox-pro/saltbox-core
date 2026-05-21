import asyncio
import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends
from git import Repo
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from saltbox_bridge_messages import CoreEmptyMessage, MasterStatus
from saltbox_core.config import SETTINGS, logger
from saltbox_core.event_bus.redis.app import default_master_broker
from saltbox_core.event_bus.redis.masters_bus import send_message_and_wait_response_to_master
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.task_templates.exceptions import RepoURLMissingException
from saltbox_core.task_templates.schemas.source import SourceOperation, SourceState, SourceType
from saltbox_core.task_templates.schemas.sshfs_file import ManifestSchema, SshfsFileCreateSchema, SshfsFileUpdateSchema
from saltbox_core.task_templates.schemas.template import TaskTemplateCreateSchema
from saltbox_core.task_templates.services.source import TemplateSourceService, get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.task_templates.utils.manifest import OrphanAuxFilesCleaner, SourceServeUpdater, create_sshfs_sync
from saltbox_core.utilities.filesystem import TreePermissionsApplicator
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException

yaml = YAML(typ='safe')


class SyncOrchestrator:
    def __init__(
        self,
        source_service: TemplateSourceService,
        template_service: TaskTemplateService,
        sshfs_files_service: SshfsFileService,
        pillar_service: PillarService,
        master_service: MasterService,
    ) -> None:
        self._source_service = source_service
        self._template_service = template_service
        self._sshfs_files_service = sshfs_files_service
        self._pillar_service = pillar_service
        self._master_service = master_service
        self._manifest: ManifestSchema | None = None
        self._local_path: Path | None = None

    async def _inject_credentials(self, repo_url: str, login: str | None, password: str | None) -> str:
        if not login or not password:
            return repo_url

        # This is a naive implementation and may not cover all cases.
        pattern = re.compile(r'^(https?://)(.*)$')
        match = pattern.match(repo_url)
        if not match:
            msg = f'Invalid repo URL: {repo_url}'
            raise ValueError(msg)
        protocol = match.group(1)
        rest = match.group(2)
        return f'{protocol}{login}:{password}@{rest}'

    async def _create_local_source_dir(self, source_id: PyObjectId) -> None:
        source = await self._source_service.get(source_id)
        local_path = Path(SETTINGS.local_repos_dir) / source.local_path

        try:
            local_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error('Failed to create local path: %s', e)
            raise

    async def _fetch(self, source_id: PyObjectId, shallow: bool = False) -> dict[str, Any]:
        source = await self._source_service.get(source_id)
        if source.source_type != SourceType.GIT_REPO:
            msg = f'Fetch is only supported for git_repo source type. Source {source_id} has type {source.source_type}.'
            raise ValueError(msg)
        if not source.repo_url:
            raise RepoURLMissingException(source_id=str(source_id))

        self._local_path = Path(SETTINGS.local_repos_dir) / source.local_path

        if self._local_path.exists() and self._local_path.is_dir():
            try:
                repo = Repo(self._local_path)
            except Exception as e:
                logger.error('Failed to access repo: %s', e)
                raise

            try:
                origin = repo.remote(name='origin')
                await asyncio.wait_for(
                    asyncio.to_thread(origin.pull),
                    timeout=60,
                )
                # return {'status': 'pulled'}
            except Exception as e:
                logger.error('Failed to pull repo: %s', e)
                shutil.rmtree(self._local_path)
                raise
        else:
            # clone
            git_kwargs: dict[str, Any] = {}
            if shallow:
                git_kwargs['depth'] = 1
                git_kwargs['single_branch'] = True

            logger.debug('Local path does not exist, cloning repo')
            raw_url = await self._inject_credentials(
                os.fspath(source.repo_url),
                source.repo_user,
                source.repo_pass.get_secret_value() if source.repo_pass else None,
            )
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(Repo.clone_from, raw_url, self._local_path, **git_kwargs),
                    timeout=SETTINGS.local_repo_sync_timeout_sec,
                )
                # return {'status': 'cloned'}
            except Exception as e:
                logger.error('Failed to clone repo: %s', e)
                shutil.rmtree(self._local_path)
                raise

        await self._parse_manifest_if_exists()
        if self._manifest and self._manifest.root != source.root:
            await self._source_service.update(source_id, {'root': self._manifest.root})

        return {'status': 'fetched'}

    async def _parse_and_save_templates(self, source_id: PyObjectId) -> None:
        parsed_schemas, _errors = await self._parse_from_local(source_id)
        # TODO: handle errors
        await self._save_templates_to_db(source_id, parsed_schemas)

    async def _parse_from_local(self, source_id: PyObjectId) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
        source = await self._source_service.get(source_id)

        parsed_schemas: dict[str, dict[str, Any]] = {}
        errors = []

        source_root = Path(SETTINGS.local_repos_dir) / source.local_path
        sls_root = source_root if not source.root else source_root / source.root

        if not sls_root.exists() or not sls_root.is_dir():
            msg = f'Local path {sls_root} does not exist or is not a directory.'
            logger.error(msg)
            raise FileNotFoundError(msg)

        pattern = re.compile(r'{#start_schema(.*?)end_schema#}', re.DOTALL)
        git_repo = Repo(source_root) if source.source_type == SourceType.GIT_REPO else None

        for sls_file in sls_root.rglob('*.sls'):
            try:
                content = sls_file.read_text(encoding='utf-8')
            except OSError as e:
                errors.append({'file': str(sls_file.relative_to(sls_root)), 'error': str(e)})
                continue

            rel_path = sls_file.relative_to(sls_root)
            name = '.'.join((*rel_path.parent.parts, rel_path.stem))
            if git_repo:
                source_hash = git_repo.git.log('--format=%H', '-1', '--', str(rel_path)) or None
            else:
                source_hash = self._make_checksum(sls_file)
            match = pattern.search(content)

            if match:
                try:
                    parsed = json.loads(match.group(1).strip())
                    if not isinstance(parsed, dict):
                        msg = f'{sls_file}: Schema is not a dictionary'
                        raise ValueError(msg)
                    if 'json_schema' not in parsed and 'title' in parsed:
                        # For v1 format without ui_schema
                        json_schema = parsed
                    else:
                        json_schema = parsed.get('json_schema', {})

                    parsed_schemas[name] = {
                        'fun': parsed.get('fun', 'state.apply'),
                        'title': json_schema.get('title', sls_file.stem),
                        'description': parsed.get('description'),
                        'defaults': parsed.get('defaults'),
                        'name': name,
                        'json_schema': json_schema,
                        'ui_schema': parsed.get('ui_schema'),
                        'source_hash': source_hash,
                        'sls_rel_path': str(rel_path),
                    }
                except json.JSONDecodeError as e:
                    errors.append({'file': str(sls_file.relative_to(sls_root)), 'error': str(e)})

        return parsed_schemas, errors

    def _make_checksum(self, file_path: Path) -> str:
        with file_path.open('rb') as file_stream:
            digest_obj = hashlib.file_digest(file_stream, 'sha256')
        return digest_obj.hexdigest()

    async def _save_templates_to_db(self, source_id: PyObjectId, parsed_schemas: dict[str, dict[str, Any]]) -> None:
        query = {
            '$and': [
                {'source_id': source_id},
                {'name': {'$nin': list(parsed_schemas.keys())}},
            ],
        }
        removed_tpl_count = await self._template_service.delete_many(query)
        logger.debug('removed_tpl_count: %s', removed_tpl_count)

        for name, schema in parsed_schemas.items():
            try:
                existing_tpl = await self._template_service.get({'name': name, 'source_id': source_id})
            except ObjectNotFoundException:
                existing_tpl = None

            if not existing_tpl:
                logger.debug('Try create: %s', name)
                await self._template_service.create(
                    data=TaskTemplateCreateSchema(**schema, source_id=source_id),
                )
            elif existing_tpl.source_hash != schema['source_hash']:
                logger.debug('Try update: %s', name)
                await self._template_service.update(query={'name': name, 'source_id': source_id}, data={**schema})

    async def _get_manifest_path(self, source_root: Path) -> Path | None:
        for name in ['manifest.yaml', 'manifest.yml']:
            path = source_root / name
            if path.is_file():
                return path
        return None

    async def _parse_manifest_if_exists(self) -> None:
        if not self._local_path:
            msg = 'Local path is not set. Cannot parse manifest.'
            logger.error(msg)
            raise ValueError(msg)

        manifest_path = await self._get_manifest_path(self._local_path)
        if not manifest_path:
            logger.debug('No manifest file found in the repo.')
            return None
        logger.debug('Manifest file found: %s', manifest_path)
        try:
            manifest_data: dict[str, Any] = yaml.load(manifest_path)
        except ScannerError as err:
            logger.error('Failed to parse manifest file: %s', err)
            return None
        self._manifest = ManifestSchema(**manifest_data)

    async def _save_sshfs_files_from_manifest(self, source_id: PyObjectId) -> None:
        if not self._manifest:
            msg = 'Manifest is not loaded. Cannot save SSHFS files.'
            logger.warning(msg)
            return

        for file_schema in self._manifest.sshfs_files.values():
            try:
                existing_file = await self._sshfs_files_service.get(
                    {'source_id': source_id, 'url': str(file_schema.url)}
                )
            except ObjectNotFoundException:
                existing_file = None

            if existing_file:
                if existing_file.checksum == file_schema.checksum:
                    logger.debug('SSHFS file already exists and is up to date: %s', file_schema.url)
                    continue
                else:
                    logger.debug('SSHFS file already exists but is outdated, updating: %s', file_schema.url)
                    await self._sshfs_files_service.update(
                        query={'source_id': source_id, 'url': str(file_schema.url)},
                        data=SshfsFileUpdateSchema(**file_schema.model_dump()),
                    )
                    continue
            else:
                file_create_schema = SshfsFileCreateSchema(
                    source_id=source_id,
                    **file_schema.model_dump(),
                )
                await self._sshfs_files_service.create(data=file_create_schema)

    async def _sync_files_to_sshfs(self, source_id: PyObjectId) -> None:
        files = await self._sshfs_files_service.get_list(query={'source_id': source_id}, skip=0, limit=0)
        for file in files:
            try:
                await create_sshfs_sync(file).sync()
                await self._sshfs_files_service.update(
                    query=file.id,
                    data={'synced_on_sshfs': True, 'last_sync_error': None},
                )
            except Exception as e:
                logger.error('Failed to sync file %s: %s', file.url, e)
                await self._sshfs_files_service.update(
                    query=file.id,
                    data={
                        'synced_on_sshfs': False,
                        'last_sync_error': str(e),
                    },
                )
                raise

    async def _serve_templates_to_serve_dir(self) -> None:
        active_sources = await self._source_service.get_list(
            query={'state': {'$in': [SourceState.DISCOVERED, SourceState.PLUGGED, SourceState.ACTIVE]}}, skip=0, limit=0
        )
        salt_modules_serve_updater = SourceServeUpdater(active_sources)
        logger.info('Updating serve dir with templates from %d active sources...', len(active_sources))
        try:
            salt_modules_serve_updater.update()
        except Exception as e:
            logger.error('Failed to update serve dir: %s', e)

    async def _cleanup_orphan_aux_files(self) -> None:
        active_sources = await self._source_service.get_list(
            query={'state': {'$in': [SourceState.DISCOVERED, SourceState.PLUGGED, SourceState.ACTIVE]}}, skip=0, limit=0
        )
        active_files = []
        for source in active_sources:
            files = await self._sshfs_files_service.get_list(query={'source_id': source.id}, skip=0, limit=0)
            active_files.extend(files)
        OrphanAuxFilesCleaner.cleanup(active_files)

    async def _update_sshfs_permissions(self) -> None:
        if not SETTINGS.sshfs_permissions:
            return
        app = TreePermissionsApplicator(SETTINGS.sshfs_permissions)
        for path in SETTINGS.sshfs_dir.glob('*'):
            app.apply_to(path)

    async def discover(self, source_id: PyObjectId) -> dict[str, Any]:
        source = await self._source_service.get(source_id)

        if source.state == SourceState.DISCOVERED:
            logger.debug('Source is already discovered, skipping fetch and parse.')
            return {'status': 'already_discovered'}

        await self._source_service.update(source_id, {'current_operation': SourceOperation.DISCOVER})

        logger.info('Source type: %s', source.source_type)

        try:
            if source.source_type == SourceType.GIT_REPO:
                await self._fetch(source_id, shallow=True)
            else:
                await self._create_local_source_dir(source_id)
        except Exception as e:
            logger.error('Fetch failed: %s', e)
            await self._source_service.update(source_id, {'state': SourceState.BROKEN, 'last_error': str(e)})
            raise

        # 2. parse and save templates to db
        try:
            await self._parse_and_save_templates(source_id)
        except Exception as e:
            logger.error('Parse failed: %s', e)
            await self._source_service.update(source_id, {'state': SourceState.BROKEN, 'last_error': str(e)})
            raise

        # 3. parse manifest and save file instances to db
        try:
            await self._save_sshfs_files_from_manifest(source_id)
        except Exception as e:
            logger.error('Manifest parsing failed: %s', e)
            await self._source_service.update(source_id, {'state': SourceState.BROKEN, 'last_error': str(e)})
            raise

        await self._source_service.update(source_id, {'state': SourceState.DISCOVERED, 'current_operation': None})
        return {'status': 'discovered'}

    async def prepare(self, source_id: PyObjectId) -> None:
        # source = await self._source_service.get(source_id)

        await self._source_service.update(source_id, {'current_operation': SourceOperation.PREPARE_SLS})
        try:
            logger.info('Syncing templates to serve dir...')
            await self._serve_templates_to_serve_dir()
        except Exception as e:
            logger.error('Failed to serve templates to serve dir: %s', e)
            await self._source_service.update(source_id, {'state': SourceState.BROKEN, 'last_error': str(e)})
            raise

        await self._source_service.update(source_id, {'current_operation': SourceOperation.PREPARE_FILES})
        try:
            logger.info('Syncing files to serve dir...')
            await self._sync_files_to_sshfs(source_id)

            logger.info('Updating SSHFS files permissions...')
            await self._update_sshfs_permissions()

            logger.info('Cleaning up orphan aux files...')
            await self._cleanup_orphan_aux_files()
        except Exception as e:
            logger.error('Failed to sync files to serve dir: %s', e)
            await self._source_service.update(source_id, {'state': SourceState.BROKEN, 'last_error': str(e)})
            raise
        await self._source_service.update(
            source_id, {'state': SourceState.PLUGGED, 'current_operation': None, 'last_error': None}
        )

    async def sync(self, source_id: PyObjectId, master_ids: list[PyObjectId]) -> None:
        # Get list of accepted masters and send them rpc notification in parallel
        await self._source_service.update(source_id, {'current_operation': SourceOperation.SYNC})
        accepted_masters = await self._master_service.get_list(
            query={'status': MasterStatus.ACCEPTED, '_id': {'$in': master_ids}}, skip=0, limit=0
        )
        if not accepted_masters:
            msg = f'No accepted masters found for source {source_id}. Skipping notification.'
            logger.warning(msg)
            await self._source_service.update(source_id, {'state': SourceState.PLUGGED, 'last_error': msg})
            return

        async with default_master_broker as broker:
            results = await asyncio.gather(
                *[
                    send_message_and_wait_response_to_master(
                        message=CoreEmptyMessage(master=master.master_id),
                        message_tag='sync_templates',
                        broker=broker,
                        response_timeout=360,
                    )
                    for master in accepted_masters
                ],
                return_exceptions=True,
            )
            logger.info('Sync results: %s', results)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            error_msg = '; '.join(str(e) for e in errors)
            await self._source_service.update(
                source_id,
                {'state': SourceState.BROKEN, 'last_error': error_msg, 'current_operation': None},
            )
            raise errors[0]

        await self._source_service.update(
            source_id,
            {
                'state': SourceState.ACTIVE,
                'current_operation': None,
                'last_error': None,
                'synced_at': datetime.now(UTC),
            },
        )

    async def remove(self, source_id: PyObjectId) -> None:
        await self._source_service.delete(source_id)

    async def create_template_from_raw(self, source_id: PyObjectId, file_name: str, content: str) -> None:
        source = await self._source_service.get(source_id)

        local_path = Path(SETTINGS.local_repos_dir) / source.local_path / f'{file_name}.sls'

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(content, encoding='utf-8')
        except OSError as e:
            logger.error('Failed to write template file: %s', e)
            raise
        await self._source_service.update(source_id, {'state': SourceState.PENDING})


async def get_sync_orchestrator(
    source_service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
    template_service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
    sshfs_files_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
) -> SyncOrchestrator:
    return SyncOrchestrator(
        source_service=source_service,
        template_service=template_service,
        sshfs_files_service=sshfs_files_service,
        pillar_service=pillar_service,
        master_service=master_service,
    )
