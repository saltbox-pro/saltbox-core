import json
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from git import Repo
from redis.asyncio import Redis

from salt_box_core.config import SETTINGS, logger


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
    def __init__(
        self, repo_url: str, local_name: str | None = None, login: str | None = None, token: str | None = None
    ) -> None:
        self.repo_url = repo_url
        self.login = login
        self.token = token
        # TODO HTTP, SSH links
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
        logger.debug('Try to clon repo %s', self.repo_url)
        if self.repo:
            logger.debug('Local path exists and is a directory, fetching latest changes')
            try:
                origin = self.repo.remotes.origin
                origin.fetch()
            except Exception as e:
                logger.error('Failed to pull repo: %s', str(e))
                if Path(self.local_path).exists():
                    logger.debug('Removing local path after failed pull')
                    shutil.rmtree(self.local_path)
                raise
        else:
            try:
                logger.debug('Local path does not exist, cloning repo')
                Repo.clone_from(self.repo_url, self.local_path, mirror=True)
                logger.debug('Repo cloned successfully')
            except Exception as e:
                logger.error('Failed to clone repo: %s', str(e))
                if Path(self.local_path).exists():
                    logger.debug('Removing local path after failed clone')
                    shutil.rmtree(self.local_path)
                raise

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
            path_parts = file.parts[salt_find_sls_index + 1 : -1]
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


class MultipleRepoSyncError(Exception):
    pass


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
