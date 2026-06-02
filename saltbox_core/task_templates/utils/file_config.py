import shutil
from pathlib import Path

from pydantic_settings import BaseSettings


class FileStorageConfig(BaseSettings):
    tmp_dir: Path = Path('_upload_tmp')
    allowed_archive_types: frozenset[str] = frozenset(ext for _, exts, _ in shutil.get_unpack_formats() for ext in exts)
    max_size: int = 4 * 1024 * 1024 * 1024
    chunk_size: int = 1024 * 1024


file_storage_config = FileStorageConfig()
