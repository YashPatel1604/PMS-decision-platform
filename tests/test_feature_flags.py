"""Feature flag defaults — legacy behavior unchanged."""

from pms_platform import feature_flags


def test_flags_default_legacy_on_approval_off() -> None:
    assert feature_flags.legacy_excel_read_enabled() is True
    assert feature_flags.legacy_excel_write_enabled() is True
    assert feature_flags.approval_workflow_enabled() is False
    assert feature_flags.cloud_storage_enabled() is False
