"""
Helper functions to work with files and directories
"""

import grp
import logging
import os
import pwd
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

logger = logging.getLogger(__name__)
UTC = timezone.utc


def user_to_uid_validator(value: Any) -> Any:
    if isinstance(value, str):
        return pwd.getpwnam(value).pw_uid
    if value is None:
        return -1
    return value


def group_to_gid_validator(value: Any) -> Any:
    if isinstance(value, str):
        value = grp.getgrnam(value).gr_gid
    if value is None:
        return -1
    return value


def oct_mode_validator(value: Any) -> int:
    if not isinstance(value, str):
        dosa = 'Expected string with an octal number in form of "777" or "0o777"'
        raise ValueError(dosa)
    return int(value, base=8)


Uid = Annotated[int, BeforeValidator(user_to_uid_validator)]
Gid = Annotated[int, BeforeValidator(group_to_gid_validator)]
OctMode = Annotated[int, BeforeValidator(oct_mode_validator)]


class TreePermissions(BaseModel):
    model_config = ConfigDict(extra='forbid')

    user: Uid = Field(
        default=-1,
        description='Name of owner or UID to set, UID MUST be a number, -1 to not to change')
    group: Gid = Field(
        default=-1,
        description='Name of group or GID to set, GID MUST be a number, -1 to not to change')
    dir_mode: OctMode | None = Field(
        default=None,
        description='Permissions mode for every file in a tree')
    file_mode: OctMode | None = Field(
        default=None,
        description='Permissions mode for every file in a tree')

    @property
    def is_chown_required(self) -> bool:
        return self.user != -1 or self.group != -1

    @property
    def is_chmod_required(self) -> bool:
        return self.file_mode is not None or self.dir_mode is not None

    @property
    def is_action_required(self) -> bool:
        return self.is_chown_required or self.is_chmod_required


class TreePermissionsApplicator:
    def __init__(self, tree_permissions: TreePermissions) -> None:
        self.tree_permissions = tree_permissions

    def apply_to(self, path: Path) -> None:
        """
        :raises PermissionError:
        :raises FileNotFoundError:
        :raises OSError:
        """
        if not self.tree_permissions.is_action_required:
            return

        logger.info('Forcing ownership and mode for %s', path)

        for root, _dirnames, filenames in path.walk():
            self._chown(root)
            self._chmod(root, self.tree_permissions.dir_mode)
            files = [root / p for p in filenames]
            for subpath in files:
                self._chown(subpath)
                self._chmod(subpath, mode=self.tree_permissions.file_mode)

    def _chown(self, path: Path) -> None:
        if not self.tree_permissions.is_chown_required:
            return
        logger.debug('Forcing owner on %s', path)
        os.chown(
            path=path,
            uid=self.tree_permissions.user,
            gid=self.tree_permissions.group,
            # We want no to touch outer pathes
            follow_symlinks=False,
        )

    def _chmod(self, path: Path, mode: int | None) -> None:
        logger.debug('Forcing mode on %s', path)
        if mode is None:
            return
        path.chmod(mode=mode, follow_symlinks=False)


def get_ctime(path: Path) -> datetime:
    """Get ctime of file or directory in form of datetime"""
    return datetime.fromtimestamp(path.stat().st_ctime, tz=UTC)


def recursive_force_remove(path: Path) -> None:
    """Ultima ratio: rm -rf incarnation"""
    if path.is_file() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def remove_older_than(path: Path, age: timedelta, log_level: int = logging.INFO) -> None:
    """
    Delete content of directory by path older than age

    Does nothing, if path is not a directory
    """
    for root, dirs, files in path.walk(top_down=False):
        threshold = datetime.now(tz=UTC) - age
        for dir in dirs:
            dir_path = root / dir
            if get_ctime(dir_path) < threshold:
                logger.log(log_level, 'Deleting dir %s older than %s', dir_path, age)
                recursive_force_remove(dir_path)
        for file in files:
            file_path = root / file
            if get_ctime(file_path) < threshold:
                logger.log(log_level, 'Deleting file %s older than %s', file_path, age)
                recursive_force_remove(file_path)


def get_latest_ctime(path: Path) -> float:
    """Get latest ctime in path recursively"""
    latest = path.stat().st_ctime
    for root, _dirs, files in path.walk():
        if (root_ctime := root.stat().st_ctime) > latest:
            latest = root_ctime
        for file in files:
            file_path = root / file
            if (file_ctime := file_path.stat().st_ctime) > latest:
                latest = file_ctime
    return latest
