import hashlib
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import httpx

from saltbox_core.config import MANIFEST_FILE_ALLOWED_NAMES, SETTINGS, logger
from saltbox_core.task_templates.exceptions import ManifestFileSyncHttpException, TaskTemplateSourceServeUpdateException
from saltbox_core.task_templates.schemas.source import TemplateSourceModel
from saltbox_core.task_templates.schemas.sshfs_file import ManifestDigest, SshfsFileModel
from saltbox_core.utilities.filesystem import TreePermissionsApplicator, get_latest_ctime, recursive_force_remove


class SshfsSyncBase(ABC):
    TMP_FILENAME_DIGEST_SIZE = 16

    def __init__(self, file_entry: SshfsFileModel) -> None:
        SETTINGS.sshfs_tmp_dir.mkdir(exist_ok=True)
        self.file_entry = file_entry
        self.dest_path = SETTINGS.sshfs_dir / file_entry.rel_path
        self.dest_digest_path = self._make_digest_path(self.dest_path)

    @abstractmethod
    def _make_digest_path(self, file: Path) -> Path: ...

    def _is_checksum_matches(self, digest_file: Path) -> bool:
        return digest_file.read_text().strip() == self.file_entry.checksum

    def _compute_and_write_checksum(self, file_path: Path) -> str:
        with file_path.open('rb') as fh:
            digest = hashlib.file_digest(fh, self.file_entry.checksum_type)
        checksum = digest.hexdigest()
        digest_path = self._make_digest_path(file_path)
        digest_path.write_text(checksum)
        return checksum

    def _purge_mismatched_digest_files(self) -> None:
        for algo in ManifestDigest:
            if algo.value == self.file_entry.checksum_type:
                continue
            stale = self.dest_digest_path.with_suffix(f'.{algo.value}')
            if stale.exists():
                logger.info('Removing stale digest file: %s', stale)
                stale.unlink()

    @abstractmethod
    def _needs_update(self) -> bool: ...

    @abstractmethod
    def _move_to_destination(self, downloaded_path: Path) -> None: ...

    def _chunk_size(self, response: httpx.Response) -> int:
        content_length = response.headers.get('content-length')
        size = int(content_length) if content_length else 0
        if size > 500 * 1024 * 1024:
            return 8 * 1024 * 1024
        return 512 * 1024

    async def sync(self) -> None:
        """Download and place file if checksum has changed."""
        self._purge_mismatched_digest_files()
        if not self._needs_update():
            logger.debug('No update needed for %s', self.dest_path)
            return

        self.dest_path.parent.mkdir(parents=True, exist_ok=True)

        headers: dict[str, str] = {}
        if self.file_entry.token:
            headers['private-token'] = self.file_entry.token.get_secret_value()

        url_str = str(self.file_entry.url)
        url_hash = hashlib.blake2b(url_str.encode(), digest_size=self.TMP_FILENAME_DIGEST_SIZE).hexdigest()
        download_path = SETTINGS.sshfs_tmp_dir / f'{url_hash}.download'
        logger.info('Syncing manifest file to SSHFS: %s', download_path)

        try:
            async with (
                httpx.AsyncClient() as client,
                client.stream('GET', url_str, headers=headers) as response,
            ):
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    try:
                        content_text = response.json()
                    except ValueError:
                        content_text = response.text
                    raise ManifestFileSyncHttpException(
                        url=url_str,
                        status_code=response.status_code,
                        content=str(content_text),
                    )

                chunk_size = self._chunk_size(response)
                with download_path.open('wb') as fh:
                    async for chunk in response.aiter_bytes(chunk_size):
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            raise ManifestFileSyncHttpException(url=url_str, detail=str(exc)) from exc

        actual_checksum = self._compute_and_write_checksum(download_path)
        if actual_checksum != self.file_entry.checksum:
            download_path.unlink(missing_ok=True)
            raise ManifestFileSyncHttpException(
                url=url_str,
                detail=f'Checksum mismatch for {self.dest_path}:'
                f' expected {self.file_entry.checksum}, got {actual_checksum}',
            )

        self._move_to_destination(download_path)
        logger.info('Synced manifest file: %s', self.dest_path)

    # TODO: check if needed to remove digest file as well
    async def remove(self) -> None:
        if self.dest_path.exists():
            if self.dest_path.is_file():
                self.dest_path.unlink()
            else:
                recursive_force_remove(self.dest_path)
        if self.dest_digest_path.exists():
            self.dest_digest_path.unlink()


class SshfsSyncPlainFile(SshfsSyncBase):
    def _make_digest_path(self, file: Path) -> Path:
        return file.parent / f'{file.name}.{self.file_entry.checksum_type}'

    def _needs_update(self) -> bool:
        if self.dest_path.exists() and not self.dest_path.is_file():
            recursive_force_remove(self.dest_path)

        if self.dest_path.exists():
            if self.dest_digest_path.exists():
                if self.dest_path.stat().st_ctime >= self.dest_digest_path.stat().st_ctime:
                    self._compute_and_write_checksum(self.dest_path)
            else:
                self._compute_and_write_checksum(self.dest_path)
        else:
            if self.dest_digest_path.exists():
                self.dest_digest_path.unlink()
            return True

        return not self._is_checksum_matches(self.dest_digest_path)

    def _move_to_destination(self, downloaded_path: Path) -> None:
        digest_path = self._make_digest_path(downloaded_path)
        shutil.move(downloaded_path, self.dest_path)
        shutil.move(digest_path, self.dest_digest_path)


class SshfsSyncArchive(SshfsSyncBase):
    def _make_digest_path(self, file: Path) -> Path:
        return file.parent / f'{file.name}.archive.{self.file_entry.checksum_type}'

    def _needs_update(self) -> bool:
        if self.dest_path.exists() and not self.dest_path.is_dir():
            recursive_force_remove(self.dest_path)

        if (
            self.dest_path.exists()
            and self.dest_digest_path.exists()
            and self._is_checksum_matches(self.dest_digest_path)
        ):
            if self.dest_digest_path.stat().st_ctime > get_latest_ctime(self.dest_path):
                return False

        if self.dest_path.exists():
            recursive_force_remove(self.dest_path)
        if self.dest_digest_path.exists():
            self.dest_digest_path.unlink()
        return True

    def _move_to_destination(self, downloaded_path: Path) -> None:
        assert self.file_entry.unpack_as is not None  # noqa: S101
        digest_path = self._make_digest_path(downloaded_path)
        try:
            shutil.unpack_archive(downloaded_path, format=self.file_entry.unpack_as, extract_dir=self.dest_path)
        except shutil.ReadError as exc:
            raise ManifestFileSyncHttpException(
                url=str(self.file_entry.url),
                detail=f'Failed to unpack as "{self.file_entry.unpack_as}": {exc}',
            ) from exc
        downloaded_path.unlink()
        shutil.move(digest_path, self.dest_digest_path)


def create_sshfs_sync(file_entry: SshfsFileModel) -> SshfsSyncBase:
    if file_entry.unpack_as is not None:
        return SshfsSyncArchive(file_entry)
    return SshfsSyncPlainFile(file_entry)


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


class OrphanAuxFilesCleaner:
    """
    Delete ALL file in SSHFS dir EXCEPT listed in keep_for_repos Manifests.

    Prefer to not run directly, beter use cleanup_orphan_aux_files() task which is
    safe from concurrent runs.
    """

    SSHFS_DIR = SETTINGS.sshfs_dir
    DRY_RUN = SETTINGS.orphan_aux_files_cleanup_dry_run

    # Following entries in SSHFS_DIR will be kept anyway
    IGNORE_LIST: ClassVar[tuple[str | Path, ...]] = ('.ssh',)

    @classmethod
    def _rm_rf(cls, path: Path) -> None:
        if not cls.DRY_RUN:
            recursive_force_remove(path)
        else:
            type_pref = 'Directory' if path.is_dir() else 'File'
            l_tpl = '%s "%s" will be deleted when dry run option will be disabled'
            logger.info(l_tpl, type_pref, path)

    @classmethod
    def get_parented_files(cls, files: list[SshfsFileModel]) -> set[Path]:
        keep_list = set()
        repo_keep_list: list[Path] = []

        for file in files:
            sync = create_sshfs_sync(file)
            repo_keep_list.append(sync.dest_path)
            repo_keep_list.append(sync.dest_digest_path)

        # Checking on Path.exists() does not affect cleanup() result
        # but may optimize matching a bit.
        keep_list |= {path for path in repo_keep_list if path.exists()}

        return keep_list

    @classmethod
    # @log_duration()
    def cleanup(cls, keep_for_repos: list[SshfsFileModel]) -> None:
        fun_name = f'{cls.cleanup.__name__}()'
        logger.debug('%s has been called', fun_name)

        root = cls.SSHFS_DIR
        keep_list = cls.get_parented_files(files=keep_for_repos)
        keep_list |= {root / entry for entry in cls.IGNORE_LIST}
        logger.debug('%s ingore list: %s', fun_name, cls.IGNORE_LIST)

        par_list = set()
        for i in keep_list:
            par_list |= set(i.parents)
        par_list -= set(cls.SSHFS_DIR.parents)

        stack = sorted(root.iterdir(), reverse=True)
        while stack:
            path = stack.pop()
            if path in keep_list:
                logger.debug('%s keeps %s', fun_name, path)
            elif path in par_list:  # entry contains some of keep_list items
                if not cls.is_outbounding_symlink(path):
                    l_tpl = '%s found symlink "%s" which leads upper, skipping'
                    logger.warning(l_tpl, fun_name, path)
                    continue
                try:
                    logger.debug('%s goes deep into %s', fun_name, path)
                    stack.extend(sorted(path.iterdir(), reverse=True))
                except NotADirectoryError:
                    l_tpl = '%s expected "%s" to be a directory, but it is not, deleting now'
                    logger.warning(l_tpl, fun_name, path)
                    cls._rm_rf(path)
            else:
                logger.info('%s deletes %s', fun_name, path)
                cls._rm_rf(path)

    @classmethod
    def is_outbounding_symlink(cls, path: Path) -> bool:
        if not path.is_absolute():
            msg = f'The {cls.is_outbounding_symlink.__name__}() works with absolute paths only'
            raise ValueError(msg)
        if not path.is_symlink():
            return True
        if path.parent not in path.resolve().parents:
            return False
        return True
