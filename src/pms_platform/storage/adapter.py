"""Private object storage adapter (local filesystem for dev)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol
from urllib.parse import quote


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


class SupabaseStorage:
    """Supabase Storage REST adapter (service_role, private bucket)."""

    def __init__(self, *, base_url: str, service_role_key: str, bucket: str) -> None:
        self._base = base_url.rstrip("/")
        self._key = service_role_key
        self._bucket = bucket

    def _object_url(self, key: str) -> str:
        safe = quote(key.lstrip("/"), safe="/")
        return f"{self._base}/storage/v1/object/{self._bucket}/{safe}"

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._key}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        import httpx

        mime = content_type or "application/octet-stream"
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                self._object_url(key),
                content=data,
                headers={**self._headers(mime), "x-upsert": "true"},
            )
            response.raise_for_status()
        return key

    def get(self, key: str) -> bytes:
        import httpx

        with httpx.Client(timeout=120.0) as client:
            response = client.get(self._object_url(key), headers=self._headers())
            response.raise_for_status()
            return response.content

    def exists(self, key: str) -> bool:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            response = client.get(self._object_url(key), headers=self._headers())
            return response.status_code == 200


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
