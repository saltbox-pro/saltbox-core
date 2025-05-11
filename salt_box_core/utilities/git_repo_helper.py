import hashlib
import json
import re
import shutil
from contextlib import asynccontextmanager
from email.message import Message
from enum import Enum
from pathlib import Path
from typing import Annotated

import httpx
from git import Repo
from pydantic import AfterValidator, BaseModel, Extra, HttpUrl, ValidationError
from redis.asyncio import Redis
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from salt_box_core.config import SETTINGS, logger

yaml = YAML()


class GitRepoError(RuntimeError): ...
class MultipleRepoSyncError(GitRepoError): ...
class GitRepoManifestError(GitRepoError): ...
class GitRepoSshfsFileSyncError(GitRepoError): ...


def validate_is_not_abs(value: Path) -> Path:
    if value.is_absolute():
        raise ValueError()
    return value


def validate_digest(value: str) -> str:
    return Digest(value).value


def _default_digest(value: ...) -> Path:
    return value


class Digest(str, Enum):
    MD5 = 'md5'
    SHA256 = 'sha256'
    SHA512 = 'sha512'


class ManifestSshfsFilesSchema(BaseModel):
    url: HttpUrl
    checksum: str
    checksum_type: Annotated[str, AfterValidator(validate_digest)] = Digest.SHA256.value
    token: str | None = None

    class Config:
        extra = Extra.forbid


NotAbsolutePath = Annotated[Path, AfterValidator(validate_is_not_abs)]


class ManifestSchema(BaseModel):
    root: NotAbsolutePath = Path()
    sshfs_files: dict[NotAbsolutePath, ManifestSshfsFilesSchema] = {}

    class Config:
        extra = Extra.forbid


class SshfsFileSyncer():
    def __init__(self, file_path: Path, file_entry: ManifestSshfsFilesSchema) -> None:
        self.file_entry = file_entry
        self.dest_path = SETTINGS.sshfs_path / file_path
        self.digest_path = self.dest_path.parent / f'{self.dest_path.name}.{self.file_entry.checksum_type}'

    def make_checksum(self) -> str:
        with open(self.dest_path, 'rb') as file_stream:
            digest_obj = hashlib.file_digest(file_stream, self.file_entry.checksum_type)
        new_checksum = digest_obj.hexdigest()
        with open(self.digest_path, 'w') as digest_file:
            digest_file.write(new_checksum)
        return new_checksum

    def purge_type_mismatched_checksums(self) -> None:
        redundant_digests = {i.value for i in Digest}
        redundant_digests.remove(self.file_entry.checksum_type)
        for digest in redundant_digests:
            path = self.digest_path.with_suffix(f'.{digest}')
            if path.exists():
                logger.info('Deleting mismatched type checksum file %s', path)
                path.unlink()

    def update_required(self) -> bool:
        # Fix general inconsistent states
        if self.digest_path.exists():
            if self.dest_path.exists():
                if self.dest_path.stat().st_ctime >= self.digest_path.stat().st_ctime:
                    logger.warning('File %s created later than checksum file, checksum will be updated')
                    self.make_checksum()
            else:
                logger.warning('Deleting dangled checksum %s', self.digest_path)
                self.digest_path.unlink()
                return True
        else:
            if self.dest_path.exists():
                logger.warning('File %s exists but has no checksum file, will create now', self.dest_path)
                self.make_checksum()
            else:
                return True

        # Compare local checksum with manifest one
        with open(self.digest_path) as digest_file:
            local_checksum = digest_file.read().strip()
        if local_checksum == self.file_entry.checksum:
            return False

        return True

    async def sync(self) -> None:
        """
        Update local file in sshfs location if required

        :raises OSError: on filesystem operations errors
        :raises SshfsFileSync:
        """
        self.purge_type_mismatched_checksums()

        if not self.update_required():
            logger.debug('Local file %s needs no update', self.dest_path)
            return

        self.dest_path.parent.mkdir(parents=True, exist_ok=True)

        headers: dict[str, str] = {}
        if self.file_entry.token:
            headers['private-token'] = self.file_entry.token

        try:
            async with (
                httpx.AsyncClient() as client,
                client.stream('GET', str(self.file_entry.url), headers=headers) as response
            ):
                response.raise_for_status()
                with open(self.dest_path, 'wb') as file:
                    async for chunk in response.aiter_bytes():
                        file.write(chunk)
        except httpx.HTTPError as err:
            raise GitRepoSshfsFileSyncError(err)
        except httpx.HTTPStatusError as err:
            raise GitRepoSshfsFileSyncError(f'Response {err.response.status_code} for {err.request.url!r}')

        cont_disp_hdr = 'content-disposition'
        header_ok = True
        if (content_dispos := response.headers.get(cont_disp_hdr)) is not None:
            message = Message()
            message[cont_disp_hdr] = content_dispos
            if message.get_content_disposition() == 'attachment':
                logger.info('Donwloaded %s to %s', message.get_filename(), self.dest_path)
            else:
                header_ok = False
                logger.warning('Content-Disposition header is not attachment for %s', response.url)
        else:
            header_ok = False
            logger.warning('Missing Content-Disposition header for %s', response.url)

        new_checksum = self.make_checksum()

        if new_checksum != self.file_entry.checksum:
            msg = f'Checksum of downloaded {self.dest_path} mismatches the manifest'
            if not header_ok:
                msg += ', Content-Disposition header was unexpected'
            raise GitRepoSshfsFileSyncError(msg)


def is_ssh_repo_url(repo_url: str) -> bool:
    """Check if the repository URL is in SSH format"""
    return repo_url.startswith('git@') or repo_url.startswith('ssh://')


class RepositoryLocker:
    """Class for managing repository synchronization locks"""

    def __init__(self, redis_client: Redis, lock_timeout: int = 3600) -> None:
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

    # def __enter__(self) -> None:
    #     """Context manager entry"""
    #     self.acquire_lock()
    #     return self

    # def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    #     """Context manager exit"""
    #     self.release_lock()
    #     return self


class GitRepoService:
    MANIFEST_FILE_ALLOWED_NAMES = ('manifest.yaml', 'manifest.yml')

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

        self.local_name = local_name or self.repo_url.rstrip('/').split('/')[-1].replace('.git', '')
        self.local_path = Path(SETTINGS.local_repos_path) / self.local_name

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

    def parse_schemas(self) -> tuple[list[dict], list[str]]:
        schemas = []
        errors = []
        for file in Path(self.local_path).rglob('*.json'):
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
                    'commit_hash': self.get_latest_commit_hash(file),
                }
                schemas.append(schema)
            except json.JSONDecodeError as e:
                msg = f'{file}: Failed to parse file ({e!s})'
                logger.error(msg)
                errors.append(msg)
        return schemas, errors

    def extract_schema(self, file: Path) -> tuple[dict | None, str | None]:
        with Path.open(file) as f:
            content = f.read()

        logger.debug('file: %s', file.parts)

        # take only path from `states` dir
        try:
            salt_find_sls_index = file.parts.index(self.local_name)
            path_parts = file.parts[salt_find_sls_index + 1: -1]
        except ValueError:
            path_parts = ()
        logger.debug('parts_after_salt_find_sls: %s', path_parts)

        name = file.stem if not path_parts else '.'.join(path_parts) + '.' + file.stem

        pattern = re.compile(r'{#start_schema(.*?)end_schema#}', re.DOTALL)
        match = pattern.search(content)

        if match:
            schema_content = match.group(1).strip()
            try:
                logger.debug('Try json_load from file: %s', file)
                schema_dict = json.loads(schema_content)
                if not isinstance(schema_dict, dict):
                    msg = f'{file}: Schema is not a dictionary'
                    return None, msg

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
                    'commit_hash': self.get_latest_commit_hash(file),
                }
                return schema, None
            except json.JSONDecodeError as e:
                msg = f'{file}: Failed to parse file ({e!s})'
                logger.error(msg)
                return None, msg
        else:
            return None, None

    def extract_schema_from_sls(self) -> tuple[list[dict], list[str]]:
        files = list(Path(self.local_path).rglob('*.sls'))
        tasks = [self.extract_schema(file) for file in files]
        # results = await asyncio.gather(*tasks)

        schemas = [result[0] for result in tasks if result[0] is not None]
        errors = [result[1] for result in tasks if result[1] is not None]

        return schemas, errors

    def get_manifest_file(self) -> Path | None:
        for name in self.MANIFEST_FILE_ALLOWED_NAMES:
            path = Path(self.local_path) / name
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
            logger.warning('Not found manifest file in repo %s, using defaults', self.local_path)
            return ManifestSchema()

        with open(path, 'r') as m_file:
            try:
                manifest_data = yaml.load(m_file)
            except ScannerError as err:
                raise GitRepoManifestError(err)

        try:
            return ManifestSchema.parse_obj(manifest_data)
        except ValidationError as err:
            raise GitRepoManifestError(err)


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
