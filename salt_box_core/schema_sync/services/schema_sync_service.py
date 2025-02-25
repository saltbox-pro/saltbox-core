import asyncio
import json
import re
from pathlib import Path

from git import Repo

from salt_box_core.config import SETTINGS, logger


class SchemaGitRepoService:
    def __init__(
        self, repo_url: str, local_name: str | None = None, login: str | None = None, token: str | None = None
    ) -> None:
        self.repo_url = repo_url
        self.login = login
        self.token = token
        if self.login and self.token and self.repo_url.startswith('https://'):
            parts = self.repo_url.split('https://')
            self.repo_url = f'https://{self.login}:{self.token}@{parts[1]}'

        self.local_name = local_name or self.repo_url.rstrip('/').split('/')[-1].replace('.git', '')
        self.local_path = './' / Path(SETTINGS.local_repos_path) / self.local_name
        self.repo: Repo
        self.salt_find_sls_dir = 'states'

    def clone_or_pull(self) -> None:
        try:
            logger.debug('Try to clon repo %s', self.repo_url)
            self.repo = Repo.clone_from(self.repo_url, self.local_path)
        except Exception as e:
            logger.error('Failed to clone repo: %s', str(e))
            logger.debug('Repo exists -> Try to pull repo')
            self.repo = Repo.init(self.local_path)
            origin = self.repo.remote(name='origin')
            origin.pull()

    def get_latest_commit_hash(self, file: Path) -> str:
        file_str = str(file).replace(f'{self.local_path}/', '')
        msg = f'Getting latest commit hash for {file_str}'
        logger.debug(msg)
        commits = list(self.repo.iter_commits(paths=file_str, max_count=1))
        return commits[0].hexsha if commits else ''

    async def extract_schema(self, file: Path) -> tuple[dict | None, str | None]:
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

        name = '.'.join(path_parts) + '.' + file.stem

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

    async def extract_schema_from_sls(self) -> tuple[list[dict], list[str]]:
        files = list(Path(self.local_path).rglob('*.sls'))
        tasks = [self.extract_schema(file) for file in files]
        results = await asyncio.gather(*tasks)

        schemas = [result[0] for result in results if result[0] is not None]
        errors = [result[1] for result in results if result[1] is not None]

        return schemas, errors

    async def parse_schemas(self) -> tuple[list[dict], list[str]]:
        schemas = []
        errors = []
        for file in Path(self.local_path).rglob('*.json'):
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
