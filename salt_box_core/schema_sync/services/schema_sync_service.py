import json
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
        self.local_path = Path(SETTINGS.local_repos_path) / self.local_name
        self.repo: Repo

    def clone_or_pull(self) -> None:
        try:
            self.repo = Repo.clone_from(self.repo_url, self.local_path)
        except Exception:
            self.repo = Repo.init(self.local_path)
            origin = self.repo.remote(name='origin')
            origin.pull()

    def get_latest_commit_hash(self, file: Path) -> str:
        file_str = str(file).replace(f'{self.local_path}/', '')
        msg = f'Getting latest commit hash for {file_str}'
        logger.debug(msg)
        commits = list(self.repo.iter_commits(paths=file_str, max_count=1))
        return commits[0].hexsha if commits else ''

    async def parse_schemas(self) -> list:
        schemas = []
        for file in Path(self.local_path).rglob('*.json'):
            try:
                content = json.loads(file.read_text())
                schema = {
                    'name': file.name.replace('.json', ''),
                    'content': content,
                    'commit_hash': self.get_latest_commit_hash(file),
                }
                schemas.append(schema)
            except json.JSONDecodeError:
                msg = f'Failed to parse {file}'
                logger.error(msg)
                pass
        return schemas
