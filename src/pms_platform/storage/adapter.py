"""Private object storage adapter (local filesystem for dev)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


class StorageAdapter(Protocol):
    """Store immutable file blobs by logical key."""

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class LocalFilesystemStorage:
    """ponytail: single-node local dir; swap for S3/Supabase in Phase 7."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        return self._root / safe

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
