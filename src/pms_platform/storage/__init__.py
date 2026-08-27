"""Storage adapter factory."""

from __future__ import annotations

from functools import lru_cache

from pms_platform.config import settings
from pms_platform.storage.adapter import LocalFilesystemStorage, StorageAdapter


@lru_cache
def get_storage() -> StorageAdapter:
    return LocalFilesystemStorage(settings.private_storage_dir)
