"""
Helper functions to work with files and directories
"""

import shutil
from pathlib import Path


def recursive_force_remove(path: Path) -> None:
    """Ultima ratio: rm -rf incarnation"""
    if path.is_file() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


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
