"""Storage adapter factory."""

from __future__ import annotations

from functools import lru_cache

from pms_platform.config import settings
from pms_platform.feature_flags import cloud_storage_enabled
from pms_platform.storage.adapter import LocalFilesystemStorage, StorageAdapter, SupabaseStorage


@lru_cache
def get_storage() -> StorageAdapter:
    if cloud_storage_enabled():
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("FEATURE_CLOUD_STORAGE=1 requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        return SupabaseStorage(
            base_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            bucket=settings.supabase_storage_bucket,
        )
    return LocalFilesystemStorage(settings.private_storage_dir)
