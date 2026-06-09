import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import httpx

from saltbox_core.config import MANIFEST_FILE_ALLOWED_NAMES, SETTINGS, logger
from saltbox_core.task_templates.exceptions import ManifestFileSyncHttpException, TaskTemplateSourceServeUpdateException
from saltbox_core.task_templates.schemas.source import TemplateSourceModel
from saltbox_core.task_templates.schemas.sshfs_file import SshfsFileModel, SshfsFileType
from saltbox_core.utilities.filesystem import TreePermissionsApplicator, recursive_force_remove
from saltbox_core.utilities.httpx_client import HttpxClientSingletoneFactory


# TODO: Remove this class and move its logic to service/orchestrator level
class SshfsSync:
    def __init__(self, httpx_client: httpx.AsyncClient | None = None) -> None:
        self._tmp_filename_digest_size = 16
        self._httpx_client = httpx_client or httpx.AsyncClient()

    def _get_dest_path(self, rel_path: str) -> Path:
        SETTINGS.sshfs_dir.mkdir(parents=True, exist_ok=True)
        dest_path = SETTINGS.sshfs_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        return dest_path

    def _get_download_path(self, url: str) -> Path:
        SETTINGS.sshfs_tmp_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.blake2b(url.encode(), digest_size=self._tmp_filename_digest_size).hexdigest()
        return SETTINGS.sshfs_tmp_dir / f'{url_hash}.download'

    def _chunk_size(self, response: httpx.Response) -> int:
        content_length = response.headers.get('content-length')
        size = int(content_length) if content_length else 0
        if size > 500 * 1024 * 1024:
            return 8 * 1024 * 1024
        return 512 * 1024

    def _move(self, src: Path, dst: Path, unpack_as: str | None = None) -> None:
        if unpack_as is not None:
            try:
                logger.info('Unpacking file %s as %s to %s', src, unpack_as, dst)
                shutil.unpack_archive(src, format=unpack_as, extract_dir=dst)
            except shutil.ReadError as exc:
                raise ManifestFileSyncHttpException(
                    detail=f'Failed to unpack as "{unpack_as}": {exc}',
                ) from exc
            src.unlink()
        else:
            shutil.move(src, dst)

    async def save_to_sshfs(self, file_entry: SshfsFileModel, tmp_path: Path | None = None) -> None:
        if tmp_path is not None:
            logger.debug('Saving file from temporary path to SSHFS: %s', tmp_path)
            self._move(tmp_path, self._get_dest_path(file_entry.rel_path), unpack_as=file_entry.unpack_as)
        elif file_entry.url is not None:
            await self._download_and_move_to_sshfs(file_entry)
        else:
            msg = 'Either tmp_path or file_entry.url must be provided'
            raise ValueError(msg)

    async def _download_and_move_to_sshfs(self, file_entry: SshfsFileModel) -> str:
        """Download URL to sshfs_dir without checksum verification. Returns computed checksum."""
        dest_path = self._get_dest_path(file_entry.rel_path)

        headers: dict[str, str] = {}
        if file_entry.token:
            headers['private-token'] = file_entry.token.get_secret_value()

        url_str = str(file_entry.url)
        download_path = self._get_download_path(url_str)
        logger.info('Syncing manifest file to SSHFS: %s', download_path)

        try:
            async with self._httpx_client.stream(method='GET', url=url_str, headers=headers) as response:
                if response.status_code != httpx.codes.OK:
                    content_text = await response.aread()
                    raise ManifestFileSyncHttpException(
                        url=url_str,
                        status_code=response.status_code,
                        content=str(content_text),
                    )

                chunk_size = self._chunk_size(response)
                digest = hashlib.new(file_entry.checksum_type)
                with download_path.open('wb') as fh:
                    async for chunk in response.aiter_bytes(chunk_size):
                        fh.write(chunk)
                        digest.update(chunk)
                actual_checksum = digest.hexdigest()
        except httpx.HTTPError as exc:
            raise ManifestFileSyncHttpException(url=url_str, detail=str(exc)) from exc
        except OSError as exc:
            logger.error('Failed to write downloaded file: %s', exc)
            raise
        if file_entry.file_type == SshfsFileType.MANIFEST and actual_checksum != file_entry.checksum:
            download_path.unlink(missing_ok=True)
            raise ManifestFileSyncHttpException(
                url=url_str,
                detail=f'Checksum mismatch for {dest_path}: expected {file_entry.checksum}, got {actual_checksum}',
            )
        self._move(download_path, dest_path, unpack_as=file_entry.unpack_as)
        return actual_checksum

    async def remove(self, file_entry: SshfsFileModel) -> None:
        dest_path = self._get_dest_path(file_entry.rel_path)
        if dest_path.exists():
            if dest_path.is_file():
                dest_path.unlink()
                parent = dest_path.parent
                while parent != SETTINGS.sshfs_dir and not any(parent.iterdir()):
                    logger.debug('Removing empty directory: %s', parent)
                    parent.rmdir()
                    parent = parent.parent
            else:
                recursive_force_remove(dest_path)


class SourceServeUpdater:
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
    IGNORE_LIST: ClassVar[tuple[str, ...]] = (
        '.git',
        '.gitignore',
        'README.md',
        *MANIFEST_FILE_ALLOWED_NAMES,
    )
    ALLOW_DUPLICATING_DIRS = SETTINGS.salt_modules_allow_duplicating_dirs
    SERVE_DIR = SETTINGS.salt_modules_serve_dir
    SERVE_DIR_PERMISSIONS = SETTINGS.salt_modules_permissions

    def __init__(self, sources: list[TemplateSourceModel]) -> None:
        self.sources = sources

    def _rsync(self, src_list: list[Path], dst: Path) -> None:
        if not src_list:
            for sp in dst.glob('*'):
                recursive_force_remove(sp)
            return

        # Trailing slash for rsync to sync content rather than dir
        rsync_src_list = [str(p) + '/' for p in src_list]
        rsync_dst = str(dst)

        cmd = ['rsync', '--archive', '--no-perms', '--no-owner', '--no-group', '--delete-after', '--delete-excluded']
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
            raise TaskTemplateSourceServeUpdateException(detail=dosa) from None
        except subprocess.CalledProcessError as err:
            logger.error('rsync exit code %i with output:\n%s', err.returncode, err.stdout)
            raise TaskTemplateSourceServeUpdateException(detail=str(err)) from None
        else:
            msg = proc.stdout.decode()
            if msg:
                logger.info('rsync output:\n%s', msg)
            else:
                logger.info('rsync succeed with no output')

    @classmethod
    def _is_ignored(cls, path: Path) -> bool:
        for ignore in (Path(i) for i in cls.IGNORE_LIST):
            if path == ignore or ignore in path.parents:
                return True
        return False

    DirContentDirs = set[Path]
    DirContentFiles = set[Path]

    @classmethod
    def _get_dir_content(cls, path: Path) -> tuple[DirContentDirs, DirContentFiles]:
        dirs: set[Path] = set()
        files: set[Path] = set()
        for cont in path.rglob('*'):
            rel_cont = cont.relative_to(path)
            if not cls._is_ignored(rel_cont):
                # We must check at least:
                #   - There are no symlinks leads to outer locations.
                #   - There are no conflicts between dir symlinks and dirs.
                if cont.is_symlink():
                    msg = f'Symlink "{rel_cont}" is found. Symlinks in SLS repoes currently are not permitted.'
                    raise TaskTemplateSourceServeUpdateException(detail=msg)
                if cont.is_dir():
                    dirs.add(rel_cont)
                elif cont.is_file():
                    files.add(rel_cont)
                else:
                    msg = f'Unexpected filesystem entry: {rel_cont}'
                    raise TaskTemplateSourceServeUpdateException(detail=msg)
        return dirs, files

    def _check_conflicts(self, dirs: list[Path]) -> None:
        dir_merge: set[Path] = set()
        file_merge: set[Path] = set()
        dups: set[Path] = set()

        for d in dirs:
            dir_cont, file_cont = self._get_dir_content(d)
            if not self.ALLOW_DUPLICATING_DIRS:
                dups |= dir_merge & dir_cont
            dups |= file_merge & file_cont
            dir_merge |= dir_cont
            file_merge |= file_cont

        # Can not mix a dir from one module and a file with the same path from another one.
        file_dir_dups = file_merge & dir_merge
        dups |= file_dir_dups

        if dups:
            raise TaskTemplateSourceServeUpdateException(detail=f'Duplicate entries found: {dups}')

    def _update_permissions(self) -> None:
        if self.SERVE_DIR_PERMISSIONS is None:
            return
        tpa = TreePermissionsApplicator(self.SERVE_DIR_PERMISSIONS)
        for path in self.SERVE_DIR.glob('*'):
            tpa.apply_to(path)

    def update(self) -> None:
        dst = self.SERVE_DIR
        src_list: list[Path] = []
        for source in self.sources:
            local_path_abs = Path(SETTINGS.local_repos_dir) / source.local_path
            if not local_path_abs.exists():
                logger.info('Skipping local repo which is not yet exists: %s', source.local_path)
                continue
            src_path = local_path_abs / source.root
            if not src_path.is_dir():
                msg = f'Path is not a regular directory: {src_path}'
                raise TaskTemplateSourceServeUpdateException(detail=msg)
            src_list.append(src_path)
        self._check_conflicts(src_list)
        self._rsync(src_list, dst)
        self._update_permissions()


async def get_sshfs_sync() -> SshfsSync:
    httpx_client = HttpxClientSingletoneFactory.get_instance()
    return SshfsSync(httpx_client=httpx_client)
