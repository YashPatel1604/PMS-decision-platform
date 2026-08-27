"""Feature flags for centralization migration.

All flags default OFF so existing local Docker behavior is unchanged until
explicitly enabled in environment or cutover runbook.
"""

from __future__ import annotations

from pms_platform.config import settings


def legacy_excel_read_enabled() -> bool:
    return settings.feature_legacy_excel_read


def legacy_excel_write_enabled() -> bool:
    return settings.feature_legacy_excel_write


def approval_workflow_enabled() -> bool:
    return settings.feature_approval_workflow


def cloud_storage_enabled() -> bool:
    return settings.feature_cloud_storage
