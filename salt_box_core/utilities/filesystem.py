"""
Helper functions to work with files and directories
"""

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)
UTC = timezone.utc


def get_ctime(path: Path) -> datetime:
    """ Get ctime of file or directory in form of datetime """
    return datetime.fromtimestamp(path.stat().st_ctime, tz=UTC)

def recursive_force_remove(path: Path) -> None:
    """ Ultima ratio: rm -rf incarnation """
    if path.is_file() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def remove_older_than(path: Path, age: timedelta, log_level: int=logging.INFO) -> None:
    """
    Delete content of directory by path older than age

    Does nothing, if path is not a directory
    """
    for root, dirs, files in path.walk(top_down=False):
        threshold = datetime.now(tz=UTC) - age
        for dir in dirs:
            dir_path = root/ dir
            if get_ctime(dir_path) < threshold:
                LOGGER.log(log_level, 'Deleting dir %s older than %s', dir_path, age)
                recursive_force_remove(dir_path)
        for file in files:
            file_path = root / file
            if get_ctime(file_path) < threshold:
                LOGGER.log(log_level, 'Deleting file %s older than %s', file_path, age)
                recursive_force_remove(file_path)


def get_latest_ctime(path: Path) -> float:
    """ Get latest ctime in path recursively """
    latest = path.stat().st_ctime
    for root, _dirs, files in path.walk():
        if (root_ctime := root.stat().st_ctime) > latest:
            latest = root_ctime
        for file in files:
            file_path = root / file
            if (file_ctime := file_path.stat().st_ctime) > latest:
                latest = file_ctime
    return latest
