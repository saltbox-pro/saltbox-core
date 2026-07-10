import asyncio
import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import anyio
import httpx
from fastapi import Depends, UploadFile
from git import Repo
from pydantic import HttpUrl
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from saltbox_bridge_messages import CoreEmptyMessage, MasterStatus
from saltbox_core.config import SETTINGS, logger
from saltbox_core.event_bus.redis.app import default_master_broker
from saltbox_core.event_bus.redis.masters_bus import send_sync_message_and_wait_response_to_master
from saltbox_core.masters.services.master_service import MasterService, get_master_service
from saltbox_core.pillars.services.pillar import PillarService, get_pillar_service
from saltbox_core.task_templates.exceptions import (
    FileNameMissingException,
    FileTooLargeException,
    FileTypeNotSupportedException,
    FileUploadException,
    GitlabApiException,
    MissingGroupIdException,
    RepoURLMissingException,
    SourceMissingFilesException,
    SourceRepoCloneException,
)
from saltbox_core.task_templates.schemas.source import (
    GitlabProjectSchema,
    SourceOperation,
    SourceState,
    SourceType,
    TemplateSourceImportFromGitSchema,
    TemplateSourceImportFromMountedSchema,
)
from saltbox_core.task_templates.schemas.sshfs_file import (
    ManifestDigest,
    ManifestSchema,
    SshfsFileCreateSchema,
    SshfsFileType,
)
from saltbox_core.task_templates.schemas.template import TaskTemplateAggregatedModel, TaskTemplateCreateSchema
from saltbox_core.task_templates.services.source import TemplateSourceService, get_tpl_source_service
from saltbox_core.task_templates.services.sshfs_file import SshfsFileService, get_sshfs_file_service
from saltbox_core.task_templates.services.template import TaskTemplateService, get_task_tpl_service
from saltbox_core.task_templates.utils.file_config import file_storage_config
from saltbox_core.task_templates.utils.manifest import SourceServeUpdater, SshfsSync, get_sshfs_sync
from saltbox_core.utilities.filesystem import TreePermissionsApplicator
from saltbox_core.utilities.httpx_client import HttpxClientSingletoneFactory
from saltbox_sdk.db.mongo.schemas_base import PyObjectId
from saltbox_sdk.exceptions import ObjectNotFoundException

yaml = YAML(typ='safe')


class SyncOrchestrator:
    def __init__(
        self,
        source_service: TemplateSourceService,
        template_service: TaskTemplateService,
        sshfs_file_service: SshfsFileService,
        pillar_service: PillarService,
        master_service: MasterService,
        sshfs_sync_service: SshfsSync,
        httpx_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._source_service = source_service
        self._template_service = template_service
        self._sshfs_file_service = sshfs_file_service
        self._pillar_service = pillar_service
        self._master_service = master_service
        self._httpx_client = httpx_client or httpx.AsyncClient()
        self._sshfs_sync_service = sshfs_sync_service
        self._manifest: ManifestSchema | None = None
        self._local_path: Path | None = None
        self._tmp_filename_digest_size = 16

    @staticmethod
    def _detect_archive_ext(file_name: str) -> str | None:
        normalized_name = file_name.lower()
        normalized_types = sorted(
            (ext.lower() for ext in file_storage_config.allowed_archive_types), key=len, reverse=True
        )
        for ext in normalized_types:
            if normalized_name.endswith(ext):
                return ext
        return None

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
        return f'{protocol}{quote(login, safe="")}:{quote(password, safe="")}@{rest}'

    async def _create_local_source_dir(self, source_id: PyObjectId) -> None:
        source = await self._source_service.get(source_id)
        local_path = Path(SETTINGS.local_repos_dir) / source.local_path

        try:
            local_path.mkdir(parents=True, exist_ok=True)
            # self._local_path = local_path
        except OSError as e:
            logger.error('Failed to create local path: %s', e)
            raise

    async def _clone_from_path(self, source_id: PyObjectId) -> None:
        source = await self._source_service.get(source_id)
        if source.source_type != SourceType.MOUNTED_REPO:
            msg = 'Clone from path is only supported for mounted_repo source type.'
            raise ValueError(msg)
        if not source.repo_mounted_path:
            msg_0 = f'Mounted path is missing for source {source_id}.'
            raise ValueError(msg_0)

        self._local_path = Path(SETTINGS.local_repos_dir) / source.local_path
        try:
            shutil.copytree(source.repo_mounted_path, self._local_path, dirs_exist_ok=True)
        except OSError as e:
            logger.error('Failed to copy from mounted path: %s', e)
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
                repo.git.update_environment(GIT_TERMINAL_PROMPT='0')
                if source.branch:
                    await asyncio.wait_for(
                        asyncio.to_thread(repo.git.pull, 'origin', source.branch),
                        timeout=SETTINGS.local_repo_sync_timeout_sec,
                    )
                else:
                    await asyncio.wait_for(
                        asyncio.to_thread(origin.pull),
                        timeout=SETTINGS.local_repo_sync_timeout_sec,
                    )
            except Exception as e:
                logger.error('Failed to pull repo: %s', e)
                raise
        else:
            git_kwargs: dict[str, Any] = {}
            if shallow:
                git_kwargs['depth'] = 1
                git_kwargs['single_branch'] = True
            if source.branch:
                git_kwargs['branch'] = source.branch

            logger.debug('Local path does not exist, cloning repo')
            raw_url = await self._inject_credentials(
                str(source.repo_url),
                source.repo_user,
                source.repo_pass.get_secret_value() if source.repo_pass else None,
            )
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        Repo.clone_from,
                        raw_url,
                        self._local_path,
                        env={'GIT_TERMINAL_PROMPT': '0'},
                        **git_kwargs,
                    ),
                    timeout=SETTINGS.local_repo_sync_timeout_sec,
                )
            except Exception as e:
                msg = f'Failed to clone repo from {raw_url}: {e}'
                logger.error(msg)
                shutil.rmtree(self._local_path, ignore_errors=True)
                raise SourceRepoCloneException(detail=msg) from None

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
            self._manifest = None
            return None
        logger.debug('Manifest file found: %s', manifest_path)
        try:
            manifest_data: dict[str, Any] = yaml.load(manifest_path)
        except ScannerError as err:
            logger.error('Failed to parse manifest file: %s', err)
            self._manifest = None
            return None
        self._manifest = ManifestSchema(**manifest_data)

    async def _save_sshfs_files_from_manifest(self, source_id: PyObjectId) -> None:
        if not self._manifest:
            logger.warning('Manifest is not loaded. Cannot save SSHFS files.')
            return

        # Only diff against MANIFEST-managed files; USER-added files are never touched here
        existing_files = await self._sshfs_file_service.get_list(
            query={'source_id': source_id, 'file_type': SshfsFileType.MANIFEST}, skip=0, limit=0
        )
        existing_files_map = {file.rel_path: file for file in existing_files}
        manifest_keys = set(self._manifest.sshfs_files.keys()) if self._manifest.sshfs_files else set()

        for rel_path in set(existing_files_map.keys()) - manifest_keys:
            await self._sshfs_file_service.delete(existing_files_map[rel_path].id)

        for rel_path, file_schema in (self._manifest.sshfs_files or {}).items():
            existing_file = existing_files_map.get(rel_path)
            if existing_file is None:
                await self._sshfs_file_service.create(
                    data=SshfsFileCreateSchema(source_id=source_id, **file_schema.model_dump())
                )
            elif (
                existing_file.checksum != file_schema.checksum
                # or existing_file.checksum_type != file_schema.checksum_type
                or existing_file.url != file_schema.url
                or existing_file.unpack_as != file_schema.unpack_as
            ):
                await self._sshfs_file_service.delete(existing_file.id)
                await self._sshfs_file_service.create(
                    data=SshfsFileCreateSchema(source_id=source_id, **file_schema.model_dump())
                )

    async def _sync_manifest_files_to_sshfs(self, source_id: PyObjectId) -> list[dict[str, str]]:
        missing_manifest_files = await self._sshfs_file_service.get_list(
            query={'source_id': source_id, 'file_type': SshfsFileType.MANIFEST, 'synced_on_sshfs': False},
            skip=0,
            limit=0,
        )
        source = await self._source_service.get(source_id)
        sync_file_errors: list[dict[str, str]] = []
        for file in missing_manifest_files:
            try:
                # If source_type is MOUNTED - check if the file exists in the sshfs_dir
                if source.source_type == SourceType.MOUNTED_REPO:
                    mounted_file_path = Path(SETTINGS.sshfs_dir) / file.rel_path
                    logger.debug('Checking if mounted file exists: %s', mounted_file_path)
                    if not mounted_file_path.exists():
                        msg = f'Mounted file not found: {mounted_file_path}'
                        raise FileNotFoundError(msg)
                else:
                    await self._sshfs_sync_service.save_to_sshfs(file)
                await self._sshfs_file_service.update(
                    query=file.id,
                    data={'synced_on_sshfs': True, 'last_sync_error': None},
                )
                logger.info('Synced manifest file: %s', file.rel_path)
            except Exception as e:
                logger.error('Failed to sync file to SSHFS: %s', e)
                await self._sshfs_file_service.update(
                    query=file.id,
                    data={'synced_on_sshfs': False, 'last_sync_error': str(e)},
                )
                sync_file_errors.append({'file': file.rel_path, 'error': str(e)})
                continue
        return sync_file_errors

    async def _serve_templates_to_serve_dir(self, source_id: PyObjectId) -> None:
        active_sources = await self._source_service.get_list(
            query={'$or': [{'_id': source_id}, {'state': {'$in': [SourceState.PLUGGED, SourceState.ACTIVE]}}]},
            skip=0,
            limit=0,
        )
        salt_modules_serve_updater = SourceServeUpdater(active_sources)
        logger.info('Updating serve dir with templates from %d active sources...', len(active_sources))
        try:
            salt_modules_serve_updater.update()
        except Exception as e:
            logger.error('Failed to update serve dir: %s', e)
            raise

    async def _update_sshfs_permissions(self) -> None:
        if not SETTINGS.sshfs_permissions:
            return
        app = TreePermissionsApplicator(SETTINGS.sshfs_permissions)
        for path in SETTINGS.sshfs_dir.glob('*'):
            app.apply_to(path)

    @staticmethod
    def _unpack_archive_strip_root(archive_path: Path, dest_path: Path, tmp_base: Path) -> None:
        """Unpack archive into dest_path, stripping the single top-level root directory if present."""
        tmp_extract = Path(tempfile.mkdtemp(dir=tmp_base))
        try:
            shutil.unpack_archive(str(archive_path), str(tmp_extract))
            extracted_entries = list(tmp_extract.iterdir())
            root_dir = (
                extracted_entries[0] if len(extracted_entries) == 1 and extracted_entries[0].is_dir() else tmp_extract
            )
            for item in root_dir.iterdir():
                shutil.move(str(item), str(dest_path / item.name))
        except Exception as e:
            raise FileUploadException(detail=f'Failed to unpack archive: {e}') from e
        finally:
            shutil.rmtree(tmp_extract, ignore_errors=True)

    async def save_and_unpack_archive(self, file: UploadFile, local_path: str) -> None:
        if file.filename is None or file.filename == '':
            raise FileNameMissingException()

        ext = self._detect_archive_ext(file.filename)
        if ext is None:
            detected_ext = ''.join(Path(file.filename).suffixes) or Path(file.filename).suffix or '.bin'
            raise FileTypeNotSupportedException(ext=detected_ext)

        safe_name = f'{uuid.uuid4()}{ext}'
        tmp_path = SETTINGS.local_repos_dir / file_storage_config.tmp_dir
        tmp_path.mkdir(parents=True, exist_ok=True)
        tmp_file_path = tmp_path / safe_name

        dest_path = SETTINGS.local_repos_dir / local_path
        dest_path.mkdir(parents=True, exist_ok=True)

        logger.debug('Saving uploaded file to temporary path: %s', tmp_path)

        total_size = 0
        try:
            async with await anyio.open_file(tmp_file_path, 'wb') as f:
                while chunk := await file.read(file_storage_config.chunk_size):
                    total_size += len(chunk)
                    if total_size > file_storage_config.max_size:
                        raise FileTooLargeException(size=total_size, max_size=file_storage_config.max_size)
                    await f.write(chunk)
        except Exception as exc:
            if tmp_file_path.exists():
                await anyio.Path(tmp_file_path).unlink()
            raise FileUploadException(detail=str(exc)) from exc

        logger.debug('File exists on disk: %s', tmp_file_path.exists())

        await asyncio.to_thread(self._unpack_archive_strip_root, tmp_file_path, dest_path, tmp_path)
        logger.debug('Archive unpacked successfully')
        # Remove the uploaded archive file
        await anyio.Path(tmp_file_path).unlink()
        logger.debug('Temporary archive file removed')

    async def discover(self, source_id: PyObjectId, task_id: str | None = None) -> dict[str, Any]:
        source = await self._source_service.get(source_id)

        if source.state == SourceState.DISCOVERED:
            logger.debug('Source is already discovered, skipping fetch and parse.')
            return {'status': 'already_discovered'}

        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.DISCOVER, 'current_task_id': task_id}
        )

        logger.info('Source type: %s', source.source_type)

        try:
            if source.source_type == SourceType.GIT_REPO:
                await self._fetch(source_id, shallow=True)
                await self._parse_manifest_if_exists()
            elif source.source_type == SourceType.MOUNTED_REPO:
                await self._clone_from_path(source_id)
                await self._parse_manifest_if_exists()
            else:
                await self._create_local_source_dir(source_id)
        except Exception as e:
            logger.error('Fetch failed: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

        try:
            await self._parse_and_save_templates(source_id)
        except Exception as e:
            logger.error('Parse failed: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

        try:
            await self._save_sshfs_files_from_manifest(source_id)
        except Exception as e:
            logger.error('Manifest parsing failed: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

        await self._source_service.update(
            source_id,
            {
                'state': SourceState.DISCOVERED,
                'current_operation': None,
                'current_task_id': None,
                'root': self._manifest.root if self._manifest else source.root,
            },
        )
        return {'status': 'discovered'}

    async def _check_if_source_local_paths_exists(self, source_id: PyObjectId) -> str:
        error = ''
        source = await self._source_service.get(source_id)
        templates = await self._template_service.get_list(query={'source_id': source_id}, skip=0, limit=0)
        local_path = Path(SETTINGS.local_repos_dir) / source.local_path
        if not local_path.exists() or not local_path.is_dir():
            error = f'Local path does not exist: {source.local_path}'
            logger.warning(error)
            return error
        for tpl in templates:
            sls_file = Path(SETTINGS.local_repos_dir) / source.local_path / (source.root or '') / tpl.sls_rel_path
            if not sls_file.exists() or not sls_file.is_file():
                logger.warning('SLS file does not exist: %s', tpl.sls_rel_path)
                error += f'SLS file does not exist: {tpl.sls_rel_path}\n'
        return error

    async def prepare(self, source_id: PyObjectId, task_id: str | None = None) -> None:
        error = await self._check_if_source_local_paths_exists(source_id)
        if error:
            logger.error('Source preparation failed:\n%s', error)
            await self._source_service.update(
                source_id,
                {
                    'state': SourceState.BROKEN,
                    'current_operation': SourceOperation.PREPARE_TEMPLATES,
                    'last_error': error,
                    'current_task_id': None,
                },
            )
            raise FileNotFoundError(error)

        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.PREPARE_TEMPLATES, 'current_task_id': task_id}
        )
        try:
            logger.info('Syncing templates to serve dir...')
            # await self._serve_templates_to_serve_dir()
            await self._serve_templates_to_serve_dir(source_id)
        except Exception as e:
            logger.error('Failed to serve templates to serve dir: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.PREPARE_FILES, 'current_task_id': task_id}
        )
        try:
            logger.info('Syncing files to serve dir...')
            sync_file_errors = await self._sync_manifest_files_to_sshfs(source_id)

            logger.info('Updating SSHFS files permissions...')
            await self._update_sshfs_permissions()

        except Exception as e:
            logger.error('Failed to sync files to serve dir: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise
        if sync_file_errors:
            error_msg = '; '.join(f'{err["file"]}: {err["error"]}' for err in sync_file_errors)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': error_msg, 'current_task_id': None}
            )
            raise SourceMissingFilesException(detail=f'Some files failed to sync to SSHFS: {error_msg}')
        else:
            await self._source_service.update(
                source_id,
                {'state': SourceState.PLUGGED, 'current_operation': None, 'last_error': None, 'current_task_id': None},
            )

    async def unplug(self, source_id: PyObjectId, task_id: str | None = None) -> None:
        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.UNPLUG, 'current_task_id': task_id}
        )
        try:
            # TODO: If namespace is required and set in manifest.yaml, we can remove all namespace dir from serve dir
            # Remove templates from serve dir
            tpls = await self._template_service.get_list(query={'source_id': source_id}, skip=0, limit=0)
            for tpl in tpls:
                sls_file = SETTINGS.salt_modules_serve_dir / tpl.sls_rel_path
                logger.debug('Attempting to remove SLS file: %s', sls_file)
                sls_file.unlink(missing_ok=True)
                parent = sls_file.parent
                while (
                    parent != SETTINGS.salt_modules_serve_dir
                    and parent.exists()
                    and parent.is_dir()
                    and not any(parent.iterdir())
                ):
                    logger.debug('Removing empty directory: %s', parent)
                    parent.rmdir()
                    parent = parent.parent
            # Remove files from SSHFS
            # sshfs_files = await self._sshfs_file_service.get_list(query={'source_id': source_id}, skip=0, limit=0)
            # for file in sshfs_files:
            #     await self._sshfs_sync_service.remove(file)
            #     await self._sshfs_file_service.update(
            #         query=file.id, data={'synced_on_sshfs': False, 'last_sync_error': None}
            #     )
        except Exception as e:
            logger.error('Failed to unplug source: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

        await self._source_service.update(
            source_id,
            {'state': SourceState.DISCOVERED, 'current_operation': None, 'last_error': None, 'current_task_id': None},
        )

    async def sync(self, source_id: PyObjectId, task_id: str | None = None) -> None:
        local_files_errors = await self._check_if_source_local_paths_exists(source_id)
        if local_files_errors:
            error_msg = '\n'.join(local_files_errors)
            logger.error('Source preparation failed:\n%s', error_msg)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': error_msg, 'current_task_id': None}
            )
            raise FileNotFoundError(error_msg)

        # Get list of accepted masters and send them rpc notification in parallel
        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.SYNC, 'current_task_id': task_id}
        )
        accepted_masters = await self._master_service.get_list(query={'status': MasterStatus.ACCEPTED}, skip=0, limit=0)
        if not accepted_masters:
            msg = f'No accepted masters found for source {source_id}. Skipping notification.'
            logger.warning(msg)
            await self._source_service.update(
                source_id, {'state': SourceState.PLUGGED, 'last_error': msg, 'current_task_id': None}
            )
            return

        async with default_master_broker as broker:
            results = await asyncio.gather(
                *[
                    send_sync_message_and_wait_response_to_master(
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
                {'state': SourceState.BROKEN, 'last_error': error_msg, 'current_task_id': None},
            )
            raise errors[0]

        await self._source_service.update(
            source_id,
            {
                'state': SourceState.ACTIVE,
                'current_operation': None,
                'last_error': None,
                'synced_at': datetime.now(UTC),
                'current_task_id': None,
            },
        )

    async def compute_checksum(self, file_path: Path, checksum_type: ManifestDigest | None = None) -> str:
        if checksum_type is None:
            checksum_type = ManifestDigest.SHA256
        with file_path.open('rb') as file_stream:
            digest_obj = hashlib.file_digest(file_stream, checksum_type.value)
        return digest_obj.hexdigest()

    async def add_user_file(
        self,
        source_id: PyObjectId,
        file_id: PyObjectId,
        tmp_path: Path | None = None,
        task_id: str | None = None,
    ) -> None:
        file_instance = await self._sshfs_file_service.get(file_id)
        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.ADD_USER_FILE, 'current_task_id': task_id}
        )

        try:
            update_data: dict[str, Any] = {'synced_on_sshfs': True, 'last_sync_error': None}
            if tmp_path:
                checksum = await self.compute_checksum(tmp_path, file_instance.checksum_type)
                update_data['checksum'] = checksum
            await self._sshfs_sync_service.save_to_sshfs(file_instance, tmp_path)
            await self._sshfs_file_service.update(query=file_id, data=update_data)
            await self._source_service.update(
                source_id,
                {'state': SourceState.PLUGGED, 'current_operation': None, 'last_error': None, 'current_task_id': None},
            )
        except Exception as e:
            logger.error('Failed to save file to SSHFS: %s', e)
            await self._sshfs_file_service.delete(file_id)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

    async def remove_source(self, source_id: PyObjectId, task_id: str | None = None) -> None:
        source = await self._source_service.get(source_id)
        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.REMOVE, 'current_task_id': task_id}
        )

        if source.source_type == SourceType.LOCAL_BUNDLE:
            is_last_local_source = await self._source_service.count(query={'source_type': SourceType.LOCAL_BUNDLE}) == 1

            if is_last_local_source:
                msg = 'Cannot remove the last local source. At least one local source must be present.'
                logger.error(msg)
                await self._source_service.update(
                    source_id,
                    {
                        'state': SourceState.DISCOVERED,
                        'current_operation': None,
                        'last_error': msg,
                        'current_task_id': None,
                    },
                )
                raise ValueError(msg)
        try:
            await self._source_service.delete(source_id)
        except Exception as e:
            logger.error('Failed to remove source: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise

    async def _create_template_db_instance_from_raw(
        self, source_id: PyObjectId, full_path: Path, rel_path: Path, content: str
    ) -> PyObjectId:
        name = '.'.join((*rel_path.parent.parts, rel_path.stem))
        pattern = re.compile(r'{#start_schema(.*?)end_schema#}', re.DOTALL)
        match = pattern.search(content)
        if not match:
            msg = f'{rel_path}: Schema block not found. Expected {{#start_schema ... end_schema#}}'
            raise ValueError(msg)

        schema_json = match.group(1).strip()
        parsed = json.loads(schema_json)
        if not isinstance(parsed, dict):
            msg = f'{rel_path}: Schema is not a dictionary'
            raise ValueError(msg)
        if 'json_schema' not in parsed and 'title' in parsed:
            # For v1 format without ui_schema
            json_schema = parsed
        else:
            json_schema = parsed.get('json_schema', {})

        tpl_data = {
            'fun': parsed.get('fun', 'state.apply'),
            'title': json_schema.get('title', rel_path.stem),
            'description': parsed.get('description'),
            'defaults': parsed.get('defaults'),
            'name': name,
            'json_schema': json_schema,
            'ui_schema': parsed.get('ui_schema'),
            'source_hash': self._make_checksum(full_path),
            'sls_rel_path': str(rel_path),
            'source_id': source_id,
        }
        return await self._template_service.create(data=tpl_data)

    async def create_template_from_raw(
        self, source_id: PyObjectId, file_name: str, content: str, task_id: str | None = None
    ) -> PyObjectId:
        source = await self._source_service.get(source_id)

        await self._source_service.update(
            source_id, {'current_operation': SourceOperation.ADD_TEMPLATE_FROM_RAW, 'current_task_id': task_id}
        )

        source_root = Path(SETTINGS.local_repos_dir) / source.local_path
        if source.namespace:
            rel_path = Path(source.namespace.strip()) / f'{file_name}.sls'
        else:
            rel_path = Path(f'{file_name}.sls')

        if source.root:
            local_path = source_root / source.root / rel_path
        else:
            local_path = source_root / rel_path

        # check if template already exists
        if local_path.exists() and local_path.is_file():
            msg = f'Template file already exists: {local_path}'
            logger.error(msg)
            await self._source_service.update(source_id, {'current_operation': None, 'current_task_id': None})
            raise FileExistsError(msg)
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(content, encoding='utf-8')
        except OSError as e:
            logger.error('Failed to write template file: %s', e)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise
        try:
            tpl_id = await self._create_template_db_instance_from_raw(source_id, local_path, rel_path, content)
        except Exception as e:
            logger.error('Failed to create template in DB: %s', e)
            local_path.unlink(missing_ok=True)
            await self._source_service.update(
                source_id, {'state': SourceState.BROKEN, 'last_error': str(e), 'current_task_id': None}
            )
            raise
        await self._source_service.update(
            source_id, {'state': SourceState.DISCOVERED, 'current_operation': None, 'current_task_id': None}
        )
        return tpl_id

    async def update_template_from_raw(self, template_id: PyObjectId, content: str, task_id: str | None = None) -> None:
        template = await self._template_service.get(template_id, projection_model=TaskTemplateAggregatedModel)

        await self._source_service.update(
            template.source_id,
            {
                'state': SourceState.PENDING,
                'current_operation': SourceOperation.UPDATE_TEMPLATE_CONTENT,
                'current_task_id': task_id,
            },
        )
        if template.source_root:
            local_path = (
                Path(SETTINGS.local_repos_dir) / template.local_path / template.source_root / template.sls_rel_path
            )
        else:
            local_path = Path(SETTINGS.local_repos_dir) / template.local_path / template.sls_rel_path

        try:
            local_path.write_text(content, encoding='utf-8')
        except OSError as e:
            logger.error('Failed to write template file: %s', e)
            raise
        await self._source_service.update(template.source_id, {'current_operation': None, 'current_task_id': None})

    async def delete_local_template(self, template_id: PyObjectId, task_id: str | None = None) -> None:
        template = await self._template_service.get(template_id, projection_model=TaskTemplateAggregatedModel)
        source = await self._source_service.get(template.source_id)
        if source.source_type not in [SourceType.LOCAL_BUNDLE, SourceType.ARCHIVE_BUNDLE]:
            msg = 'Deleting template is only supported for local sources.'
            logger.error(msg)
            raise ValueError(msg)

        await self._source_service.update(
            template.source_id,
            {
                'state': SourceState.PENDING,
                'current_operation': SourceOperation.DELETE_LOCAL_TEMPLATE,
                'current_task_id': task_id,
            },
        )
        if template.source_root:
            local_path = (
                Path(SETTINGS.local_repos_dir) / template.local_path / template.source_root / template.sls_rel_path
            )
        else:
            local_path = Path(SETTINGS.local_repos_dir) / template.local_path / template.sls_rel_path

        try:
            local_path.unlink(missing_ok=True)
        except OSError as e:
            logger.error('Failed to delete template file: %s', e)
            raise
        await self._source_service.update(template.source_id, {'current_operation': None, 'current_task_id': None})

    async def _get_gitpab_projects_list(self) -> list[GitlabProjectSchema]:
        if not SETTINGS.gitlab_group_id:
            raise MissingGroupIdException()

        url = f'{SETTINGS.gitlab_base_url}/api/v4/groups/{SETTINGS.gitlab_group_id}/projects'
        headers = {}
        if SETTINGS.gitlab_token:
            headers['Authorization'] = f'Bearer {SETTINGS.gitlab_token}'

        query_params = {
            'archived': 'false',
            'per_page': '200',
            'page': '0',
            'order_by': 'id',
            'sort': 'asc',
        }

        response = await self._httpx_client.get(url, headers=headers, params=query_params)

        if not response.is_success:
            raise GitlabApiException(
                status_code=response.status_code, detail=f'GitLab API request failed: {response.text}'
            )

        projects_data = response.json()

        return [
            GitlabProjectSchema(**item)
            for item in projects_data
            if item.get('marked_for_deletion_on') is None and item.get('marked_for_deletion_at') is None
        ]

    async def create_sources_from_gitlab(self) -> None:
        projects = await self._get_gitpab_projects_list()
        source_ids_to_discover = []
        for project in projects:
            try:
                existing_source = await self._source_service.get(query={'repo_url': project.http_url_to_repo})
            except ObjectNotFoundException:
                existing_source = None
            if existing_source:
                if existing_source.state in [SourceState.DISCOVERED]:
                    await self._source_service.update(
                        existing_source.id,
                        {
                            'name': project.name,
                            'description': project.description or '',
                            'repo_user': 'user' if SETTINGS.gitlab_token else None,
                            'repo_pass': SETTINGS.gitlab_token if SETTINGS.gitlab_token else None,
                            'state': SourceState.PENDING,
                        },
                    )
                    source_ids_to_discover.append(existing_source.id)
                else:
                    logger.debug(
                        f'Source for repo {project.http_url_to_repo} already exists with '
                        f'state {existing_source.state}, skipping update'
                    )
                continue

            source_in = TemplateSourceImportFromGitSchema(
                name=project.name,
                description=project.description or '',
                repo_url=HttpUrl(project.http_url_to_repo),
                repo_user='user' if SETTINGS.gitlab_token else None,
                repo_pass=SETTINGS.gitlab_token if SETTINGS.gitlab_token else None,
                branch=project.default_branch,
            )

            created_source_id = await self._source_service.create_from_url(data=source_in)
            source_ids_to_discover.append(created_source_id)

        for source_id in source_ids_to_discover:
            try:
                await self.discover(source_id)
            except Exception as e:
                logger.error(f'Failed to discover source {source_id} created from GitLab project: {e}')

    async def create_sources_from_mounted(self) -> None:
        mounted_dir = anyio.Path('/mnt/config-boxes/')
        if not await mounted_dir.exists() or not await mounted_dir.is_dir():
            msg = 'Mounted directory /mnt/config-boxes/ does not exist or is not a directory.'
            logger.warning(msg)
            raise FileNotFoundError(msg)

        mounted_repos = [
            d
            async for d in mounted_dir.iterdir()
            if await d.is_dir() and await (d / '.git').exists()
            # and await (d / 'manifest.yaml').exists()
        ]

        for repo_path in mounted_repos:
            try:
                existing_source = await self._source_service.get(
                    query={'source_type': SourceType.MOUNTED_REPO, 'repo_mounted_path': str(repo_path)}
                )
            except ObjectNotFoundException:
                existing_source = None
            if existing_source:
                logger.debug(f'Source for mounted repo {repo_path!s} already exists, skipping creation')
                continue

            source_in = TemplateSourceImportFromMountedSchema(
                name=str(repo_path.relative_to(mounted_dir)),
                repo_mounted_path=str(repo_path),
            )
            created_source_id = await self._source_service.create_from_mounted_path(data=source_in)
            try:
                await self.discover(created_source_id)
            except Exception as e:
                logger.error(f'Failed to discover source {created_source_id} created from mounted repo: {e}')


async def get_sync_orchestrator(
    source_service: Annotated[TemplateSourceService, Depends(get_tpl_source_service)],
    template_service: Annotated[TaskTemplateService, Depends(get_task_tpl_service)],
    sshfs_file_service: Annotated[SshfsFileService, Depends(get_sshfs_file_service)],
    pillar_service: Annotated[PillarService, Depends(get_pillar_service)],
    master_service: Annotated[MasterService, Depends(get_master_service)],
    sshfs_sync_service: Annotated[SshfsSync, Depends(get_sshfs_sync)],
) -> SyncOrchestrator:
    httpx_client = HttpxClientSingletoneFactory.get_instance()
    return SyncOrchestrator(
        source_service=source_service,
        template_service=template_service,
        sshfs_file_service=sshfs_file_service,
        pillar_service=pillar_service,
        master_service=master_service,
        sshfs_sync_service=sshfs_sync_service,
        httpx_client=httpx_client,
    )
