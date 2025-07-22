import hashlib
import json
import logging
import re
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from email.message import Message
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar, Self

import httpx
from git import Repo
from pydantic import ValidationError
from redis.asyncio import Redis
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from salt_box_core.config import MANIFEST_FILE_ALLOWED_NAMES, SETTINGS
from salt_box_core.settings.schemas.sls_repos_schemas import (
    ManifestDigest,
    ManifestSchema,
    ManifestSshfsFilesSchema,
    SettingsSlsRepoModel,
)
from salt_box_core.utilities.filesystem import get_latest_ctime, recursive_force_remove

logger = logging.getLogger(__name__)
yaml = YAML()


class GitRepoError(RuntimeError): ...


class MultipleRepoSyncError(GitRepoError): ...


class GitRepoSshfsFileSyncError(GitRepoError): ...


class SlsRepoError(RuntimeError): ...


class SlsRepoManifestError(SlsRepoError): ...


class SlsRepoExtractingSchemaError(SlsRepoError): ...


class SlsReposServeUpdaterError(GitRepoError): ...


class SshfsSyncBase(ABC):
    TMP_DIR = SETTINGS.sshfs_tmp_dir

    def __init__(self, file_path: Path, file_entry: ManifestSshfsFilesSchema) -> None:
        self.TMP_DIR.mkdir(exist_ok=True)
        self.file_entry = file_entry
        self.dest_path = SETTINGS.sshfs_dir / file_path
        self.dest_digest_path = self.make_digest_path(self.dest_path)

    @abstractmethod
    def make_digest_path(self, file: Path) -> Path:
        """Retruns path to digest file for file"""

    def is_checksum_matches(self, digest_file: Path) -> bool:
        """Compare checksum from file with manifest one"""
        with digest_file.open() as fstream:
            local_checksum = fstream.read().strip()
        return local_checksum == self.file_entry.checksum

    def make_checksum(self, file_path: Path) -> str:
        with file_path.open('rb') as file_stream:
            digest_obj = hashlib.file_digest(file_stream, self.file_entry.checksum_type)
        new_checksum = digest_obj.hexdigest()
        digest_path = self.make_digest_path(file_path)
        with digest_path.open('w') as digest_file:
            digest_file.write(new_checksum)
        return new_checksum

    def purge_type_mismatched_checksums(self) -> None:
        redundant_digests = {i.value for i in ManifestDigest}
        redundant_digests.remove(self.file_entry.checksum_type)
        for digest in redundant_digests:
            path = self.dest_digest_path.with_suffix(f'.{digest}')
            if path.exists():
                logger.info('Deleting mismatched type checksum file %s', path)
                path.unlink()

    @abstractmethod
    def check_local_data(self) -> bool:
        """
        Method should sane files and check if updated required for four main states:
         - No local digest and no local data
         - Local digest and local data presented
         - Local data presented with no local digest (possibly interrupted copying)
         - Local digest presented with no loca data (digest is dangled)

        :return bool: does donwnloading data required
        """

    def get_origin_filename(self, response: httpx.Response) -> str:
        cont_disp_hdr = 'content-disposition'
        content_dispos = response.headers.get(cont_disp_hdr)
        logger.debug('Content-Disposition header was %s for %s', content_dispos, response.url)
        message = Message()
        message[cont_disp_hdr] = content_dispos
        if message.get_content_disposition() != 'attachment':
            logger.warning('Content-Disposition header is not attachment for %s', response.url)
        if (filename := message.get_filename()) is not None:
            return filename
        else:
            msg = f'Failed to obtain origin filename from content-disposal header for {response.url}'
            raise GitRepoSshfsFileSyncError(msg)

    @abstractmethod
    def move_to_destination(self, file_path: Path) -> None:
        """Handle donwnloaded file to put expected data to destination"""

    def _get_chunk_size(self, response: httpx.Response) -> int:
        """
        Determine chunk size for downloading file based on its size

        :param response: httpx.Response object
        :return: chunk size in bytes
        """
        content_length = response.headers.get('content-length')
        if content_length is not None:
            file_size = int(content_length)
        else:
            file_size = 0

        logger.debug('File size: %d Mb', file_size / 1024 / 1024)  # Convert to MB

        if file_size > 500 * 1024 * 1024:  # >500 МБ
            chunk_size = 8 * 1024 * 1024  # 8 МБ
        else:
            chunk_size = 512 * 1024  # 512 КБ

        logger.debug('Chunk size: %d Kb', chunk_size / 1024)  # Convert to KB
        return chunk_size

    async def sync(self) -> None:
        """
        Update local file in sshfs location if required

        :raises OSError: on filesystem operations errors
        :raises SshfsFileSync:
        """
        self.purge_type_mismatched_checksums()

        if not self.check_local_data():
            logger.debug('Local file %s needs no update', self.dest_path)
            return

        self.dest_path.parent.mkdir(parents=True, exist_ok=True)

        headers: dict[str, str] = {}
        if self.file_entry.token:
            headers['private-token'] = self.file_entry.token

        try:
            async with (
                httpx.AsyncClient() as client,
                client.stream('GET', str(self.file_entry.url), headers=headers) as response,
            ):
                response.raise_for_status()
                origin_filename = self.get_origin_filename(response)
                download_path = self.TMP_DIR / origin_filename

                chunk_size = self._get_chunk_size(response)

                with download_path.open('wb') as file:
                    total_written = 0
                    async for chunk in response.aiter_bytes(chunk_size):
                        file.write(chunk)
                        total_written += len(chunk)
                        if total_written % (100 * 1024 * 1024) < chunk_size:
                            logger.debug('Downloaded %d MB to %s', total_written // (1024 * 1024), download_path)
        except httpx.HTTPError as err:
            raise GitRepoSshfsFileSyncError(err) from None
        except httpx.HTTPStatusError as err:
            msg = f'Response {err.response.status_code} for {err.request.url!r}'
            raise GitRepoSshfsFileSyncError(msg) from None

        logger.debug('Downloaded %s to %s', origin_filename, download_path)

        new_checksum = self.make_checksum(download_path)

        if new_checksum != self.file_entry.checksum:
            msg = f'Checksum of downloaded {self.dest_path} mismatches the manifest'
            raise GitRepoSshfsFileSyncError(msg)

        self.move_to_destination(download_path)

        logger.info('File has been synced: %s', self.dest_path)


class SshfsSyncPlainFile(SshfsSyncBase):
    def make_digest_path(self, file: Path) -> Path:
        return file.parent / f'{file.name}.{self.file_entry.checksum_type}'

    def check_local_data(self) -> bool:
        # Fix general inconsistent states
        if self.dest_path.exists() and not self.dest_path.is_file():
            logger.warning('Is not a regular file and will be deleted: %s')
            recursive_force_remove(self.dest_path)

        if self.dest_path.exists():
            if self.dest_digest_path.exists():
                if self.dest_path.stat().st_ctime >= self.dest_digest_path.stat().st_ctime:
                    logger.warning('File %s created later than checksum file, checksum will be updated', self.dest_path)
                    self.make_checksum(self.dest_path)
            else:
                logger.warning('File %s exists but has no checksum file, will create now', self.dest_path)
                self.make_checksum(self.dest_path)
        else:
            if self.dest_digest_path.exists():
                logger.warning('Deleting dangled checksum %s', self.dest_digest_path)
                self.dest_digest_path.unlink()
                return True
            else:
                return True

        if self.is_checksum_matches(self.dest_digest_path):
            return False

        return True

    def move_to_destination(self, file_path: Path) -> None:
        digest_path = self.make_digest_path(file_path)
        shutil.move(file_path, self.dest_path)
        shutil.move(digest_path, self.dest_digest_path)
        logger.debug('Moved %s to %s', file_path, self.dest_path)


class SshfsSyncArchive(SshfsSyncBase):
    def make_digest_path(self, file: Path) -> Path:
        return file.parent / f'{file.name}.archive.{self.file_entry.checksum_type}'

    def check_local_data(self) -> bool:
        if self.dest_path.exists() and not self.dest_path.is_dir():
            logger.warning('Is not a directory and will be deleted to unpack archive: %s', self.dest_path)
            recursive_force_remove(self.dest_path)

        # Only no need to sync if:
        # - Have both digest and directory
        # - Digest matches with manifest
        # - Digest is newer than all directory content
        if (
            self.dest_path.exists()
            and self.dest_digest_path.exists()
            and self.is_checksum_matches(self.dest_digest_path)
        ):
            digest_ctime = self.dest_digest_path.stat().st_ctime
            latest_ctime = get_latest_ctime(self.dest_path)
            if digest_ctime > latest_ctime:
                return False

        if self.dest_path.exists():
            logger.warning('Will be deleted to unpack archive: %s', self.dest_path)
            recursive_force_remove(self.dest_path)
        if self.dest_digest_path.exists():
            logger.warning('Dangled digest will be deleted: %s', self.dest_digest_path)
            self.dest_digest_path.unlink()

        return True

    def move_to_destination(self, file_path: Path) -> None:
        digest_path = self.make_digest_path(file_path)
        shutil.unpack_archive(file_path, extract_dir=self.dest_path)
        file_path.unlink()
        shutil.move(digest_path, self.dest_digest_path)
        logger.debug('Umpacked %s to %s', file_path, self.dest_path)


def create_sshfs_sync(file_path: Path, file_entry: ManifestSshfsFilesSchema) -> SshfsSyncBase:
    if file_entry.unpack:
        return SshfsSyncArchive(file_path, file_entry)
    return SshfsSyncPlainFile(file_path, file_entry)


def is_ssh_repo_url(repo_url: str) -> bool:
    """Check if the repository URL is in SSH format"""
    return repo_url.startswith('git@') or repo_url.startswith('ssh://')


class RepositoryLocker:
    """Class for managing repository synchronization locks"""

    def __init__(self, redis_client: Redis, lock_timeout: int = SETTINGS.local_repo_sync_timeout_sec) -> None:
        self.redis = redis_client
        self.lock_timeout = lock_timeout

    async def acquire_lock(self, repo_id: str) -> bool:
        """Acquiring a lock"""
        lock_key = f'repo_lock:{repo_id}'
        locked = await self.redis.set(lock_key, '1', ex=self.lock_timeout, nx=True)
        return bool(locked)

    async def release_lock(self, repo_id: str) -> None:
        """Releasing a lock"""
        lock_key = f'repo_lock:{repo_id}'
        await self.redis.delete(lock_key)

    async def is_locked(self, repo_id: str) -> bool:
        """Checking if a lock is active"""
        lock_key = f'repo_lock:{repo_id}'
        return bool(await self.redis.get(lock_key))


class GitRepoService:
    def __init__(
        self, repo_url: str, local_name: str | None = None, login: str | None = None, token: str | None = None
    ) -> None:
        self.repo_url = repo_url
        self.login = login
        self.token = token
        # TODO (a.karmanov): HTTP, SSH links
        if self.login and self.token and self.repo_url.startswith('https://'):
            parts = self.repo_url.split('https://')
            self.repo_url = f'https://{self.login}:{self.token}@{parts[1]}'

        self.local_name = local_name or uuid.uuid4().hex
        self.local_path = Path(SETTINGS.local_repos_dir) / self.local_name

    @classmethod
    def from_model(cls, model: SettingsSlsRepoModel) -> Self:
        url = model.get_repo_url_as_str()
        return cls(
            repo_url=url,
            local_name=model.local_path,
            login=model.repo_user,
            token=model.repo_pass.get_secret_value() if model.repo_pass else None,
        )

    @property
    def repo(self) -> Repo | None:
        if self.local_path.exists() and self.local_path.is_dir():
            try:
                return Repo(self.local_path)
            except Exception as e:
                logger.error('Failed to access repo: %s', str(e))
                return None
        return None

    def clone_or_pull(self) -> None:
        logger.debug('Try to clone repo %s', self.repo_url)
        if self.repo:
            logger.debug('Local path exists and is a directory, pulling latest changes')
            try:
                origin = self.repo.remote(name='origin')
                origin.pull()
            except Exception:
                self.purge()
                raise
        else:
            logger.debug('Local path does not exist, cloning repo')
            try:
                # TODO (a.baikov): look for kill_after_timeout=SETTINGS.local_repo_sync_timeout_sec
                Repo.clone_from(self.repo_url, self.local_path)
                logger.debug('Repo cloned successfully')
            except Exception:
                self.purge()
                raise

    def purge(self) -> None:
        if Path(self.local_path).exists():
            logger.debug('Removing repository %s', self.local_path)
            shutil.rmtree(self.local_path)

    def get_latest_commit_hash(self, file: Path) -> str:
        file_str = str(file).replace(f'{self.local_path}/', '')
        if self.repo is None:
            msg = 'Repository is not initialized'
            logger.error(msg)
            raise Exception(msg)
        commits = list(self.repo.iter_commits(paths=file_str, max_count=1))
        return commits[0].hexsha if commits else ''


def parse_schemas(schema_repo: GitRepoService) -> tuple[list[dict], list[str]]:
    schemas = []
    errors = []
    for file in Path(schema_repo.local_path).rglob('*.json'):
        if any(part in file.parts for part in ['.vscode', '.idea']):
            logger.debug('Exclude file: %s', file)
            continue
        try:
            content = json.loads(file.read_text())
            if not isinstance(content, dict):
                msg = f'{file}: Schema is not a dictionary'
                errors.append(msg)

            if 'json-schema' not in content.keys() and 'title' in content.keys():
                json_schema = content
            else:
                json_schema = content.get('json_schema', {})

            schema = {
                'name': file.name.replace('.json', ''),
                'json_schema': json_schema,
                'ui_schema': content.get('ui_schema', {}),
                'commit_hash': schema_repo.get_latest_commit_hash(file),
            }
            schemas.append(schema)
        except json.JSONDecodeError as e:
            msg = f'{file}: Failed to parse file ({e!s})'
            logger.error(msg)
            errors.append(msg)
    return schemas, errors


class SlsRepoService:
    # TODO ( a.karmanov ) :: Support plain file/archive repo
    def __init__(self, repo_model: SettingsSlsRepoModel) -> None:
        self.repo_model = repo_model

    @property
    def local_path(self) -> str:
        return self.repo_model.local_path

    @property
    def local_path_abs(self) -> Path:
        if not self.local_path:
            err_msg = 'Empty local_path, uninitialized?'
            raise SlsRepoError(err_msg)
        return Path(SETTINGS.local_repos_dir) / self.local_path

    @cached_property
    def storage(self) -> GitRepoService:
        return GitRepoService.from_model(self.repo_model)

    def get_manifest_file(self) -> Path | None:
        for name in MANIFEST_FILE_ALLOWED_NAMES:
            path = self.local_path_abs / name
            if path.is_file():
                return path
        return None

    def parse_manifest(self) -> ManifestSchema:
        """
        :raises OSError: on filesystem operations errors
        :raises GitRepoManifestError:
        """
        path = self.get_manifest_file()
        if path is None:
            logger.warning(
                "Not found manifest file in salt module repo '%s', using defaults",
                self.local_path_abs,
            )
            return ManifestSchema()

        with path.open() as m_file:
            try:
                manifest_data = yaml.load(m_file)
            except ScannerError as err:
                raise SlsRepoManifestError(err) from None

        try:
            return ManifestSchema.parse_obj(manifest_data)
        except ValidationError as err:
            raise SlsRepoManifestError(err) from None

    def extract_schemas(self) -> tuple[list[dict], list[str]]:
        files = list(Path(self.storage.local_path).rglob('*.sls'))
        schemas = []
        errors = []

        for file in files:
            try:
                schema = self._extract_schema(file)
            except SlsRepoExtractingSchemaError as err:
                errors.append(str(err))
            else:
                if schema is not None:
                    schemas.append(schema)

        return schemas, errors

    def _extract_schema(self, file: Path) -> dict[str, Any] | None:
        with Path.open(file) as f:
            content = f.read()

        logger.debug('SLS file parts: %s', file.parts)

        # take only path from `states` dir
        try:
            salt_find_sls_index = file.parts.index(self.storage.local_name)
            path_parts = file.parts[salt_find_sls_index + 1 : -1]
        except ValueError:
            path_parts = ()  # FIXME Chego kuda?
        logger.debug('Parts after salt_find_sls_index: %s', path_parts)

        name = '.'.join((*path_parts, file.stem))

        pattern = re.compile(r'{#start_schema(.*?)end_schema#}', re.DOTALL)
        match = pattern.search(content)

        if match:
            schema_content = match.group(1).strip()
            try:
                logger.debug('Try json_load from file: %s', file)
                schema_dict = json.loads(schema_content)
                if not isinstance(schema_dict, dict):
                    msg = f'{file}: Schema is not a dictionary'
                    raise SlsRepoExtractingSchemaError(msg)

                if 'json_schema' not in schema_dict.keys() and 'title' in schema_dict.keys():
                    # For v1 format without ui_schema
                    json_schema = schema_dict
                else:
                    json_schema = schema_dict.get('json_schema', {})

                logger.debug('resolved path: %s', file.resolve())

                schema = {
                    'fun': 'state.apply',
                    'title': json_schema['title'],
                    'name': name,
                    'json_schema': json_schema,
                    'ui_schema': schema_dict.get('ui_schema', {}),
                    'sls_content': content,
                    'commit_hash': self.storage.get_latest_commit_hash(file),
                }
                return schema
            except json.JSONDecodeError as e:
                msg = f'{file}: Failed to parse file ({e!s})'
                logger.error(msg)
                raise SlsRepoExtractingSchemaError(msg) from None
        else:
            return None


class SlsReposServeUpdater:
    """
    Sync active Conf Boxes files into directory to serve for Salt Masters.

    Prefer to not run directly, beter use sync_sls_repos_to_serve_dir() task which is
    safe from concurrent runs.
    """

    # Path will be ignored in conflict check and excluded from sync.
    # DO NOT USE GLOBS:
    #  - Items will be checked on being equal or being a subpass of a value on conlicts check.
    #  - Items will be passed to rsync `--exclude` as is. Trailing `/` is significant.
    # Rsync excludes to not to sync to serve location.
    IGNORE_LIST: ClassVar = ('.git', '.gitignore', 'README.md', *MANIFEST_FILE_ALLOWED_NAMES)

    def __init__(self, repos: list[SettingsSlsRepoModel]) -> None:
        self.repos = repos

    def _rsync(self, src_list: list[Path], dst: Path) -> None:
        if not src_list:
            for sp in dst.glob('*'):
                recursive_force_remove(sp)
            return

        # Trailing slash for rsync to sync content rather than dir
        rsync_src_list = [str(p) + '/' for p in src_list]
        rsync_dst = str(dst)

        cmd = ['rsync', '--archive', '--delete-after', '--delete-excluded']
        for i in self.IGNORE_LIST:
            cmd.append('--exclude')
            cmd.append(i)
        cmd.extend(rsync_src_list)
        cmd.append(rsync_dst)
        logger.debug('Prepared command: %s', cmd)
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)  # noqa
        except FileNotFoundError:
            dosa = 'No rsync binary in $PATH'
            raise SlsReposServeUpdaterError(dosa) from None
        except subprocess.CalledProcessError as err:
            logger.error('rsync exit code %i with output:\n%s', err.returncode, err.stdout)
            raise SlsReposServeUpdaterError(err) from None
        else:
            msg = proc.stdout.decode()
            if msg:
                logger.info('rsync output:\n%s', msg)
            else:
                logger.info('rsync succeed with no output')

    @classmethod
    def _is_ignored(cls, path: Path) -> bool:
        for ignore in cls.IGNORE_LIST:
            ignore = Path(ignore)
            if path == ignore or ignore in path.parents:
                return True
        return False

    @classmethod
    def _get_dir_content(cls, path: Path) -> set:
        result: set[Path] = set()
        for cont in path.rglob('*'):
            rel_cont = cont.relative_to(path)
            if not cls._is_ignored(rel_cont):
                result.add(rel_cont)
        return result

    def _check_conflicts(self, dirs: list[Path]) -> None:
        merge: set[Path] = set()
        dups: set[Path] = set()
        for d in dirs:
            content = self._get_dir_content(d)
            dups |= merge & content
            merge |= content
        if dups:
            for dup in dups:
                logger.error('Path exists in multiple Salt modules: %s', dup)
            msg = 'Conflicting paths have been found in Salt modules, check log'
            raise SlsReposServeUpdaterError(msg)

    def update(self) -> None:
        dst = SETTINGS.salt_modules_serve_dir
        src_list: list[Path] = []
        for repo in self.repos:
            sls_repo = SlsRepoService(repo)
            manifest = sls_repo.parse_manifest()
            if not sls_repo.local_path_abs.exists():
                logger.info('Skipping local repo which is not yet exists: %s', repo.local_path)
                continue
            src_path = sls_repo.local_path_abs / manifest.root
            if not src_path.is_dir():
                msg = f'Path is not a regular directory: {src_path}'
                raise SlsReposServeUpdaterError(msg)
            src_list.append(src_path)
        self._check_conflicts(src_list)
        self._rsync(src_list, dst)


@asynccontextmanager
async def repository_lock(redis: Redis, repo_url: str):  # type: ignore[no-untyped-def]
    """Контекстный менеджер для блокировки репозитория во время синхронизации."""
    locker = RepositoryLocker(redis)

    if await locker.is_locked(repo_url):
        msg = 'Another task is running for the same repo'
        logger.debug(msg)
        raise MultipleRepoSyncError(msg)

    await locker.acquire_lock(repo_url)
    logger.debug('Repo locked')

    try:
        yield
    finally:
        await locker.release_lock(repo_url)
        logger.debug('Repo unlocked')
