"""Self-check: DailyEditBackup local + Graph path selection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pms_platform.jobs.onedrive_daily_backup import (
    maybe_run_onedrive_daily_backup,
    resolve_backup_bytes,
    run_onedrive_daily_backup,
)


def test_resolve_prefers_canonical_disk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.daily_edit_dir",
        tmp_path,
    )
    path = tmp_path / "Charts.xlsx"
    path.write_bytes(b"charts-bytes")
    got = resolve_backup_bytes(None, "charts")
    assert got == ("Charts.xlsx", b"charts-bytes")


def test_run_backup_writes_four_local(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "DailyEditBackup"
    src.mkdir()
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.daily_edit_dir",
        src,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_dir",
        dest,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_enabled",
        True,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup._use_graph",
        lambda: False,
    )
    for name in (
        "PMS_ClientPortfolio.xlsx",
        "Charts.xlsx",
        "SCA_LLP Stock Holding.xlsx",
        "PivotPoints.xlsx",
    ):
        (src / name).write_bytes(name.encode())

    result = run_onedrive_daily_backup(None)
    assert result["ok"] is True
    assert result["via"] == "local"
    assert (dest / "Charts.xlsx").read_bytes() == b"Charts.xlsx"


def test_run_backup_graph(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.daily_edit_dir",
        src,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_enabled",
        True,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_graph_folder",
        "PMS-Decision-Platform/DailyEditBackup",
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup._use_graph",
        lambda: True,
    )
    monkeypatch.setattr(
        "pms_platform.storage.onedrive_graph.access_token_from_refresh",
        lambda **_: "tok",
    )
    uploaded: list[str] = []

    def _put(path: str, data: bytes, *, access_token: str, client=None):
        uploaded.append(path)

    monkeypatch.setattr("pms_platform.storage.onedrive_graph.put_drive_file", _put)
    for name in (
        "PMS_ClientPortfolio.xlsx",
        "Charts.xlsx",
        "SCA_LLP Stock Holding.xlsx",
        "PivotPoints.xlsx",
    ):
        (src / name).write_bytes(b"x")

    result = run_onedrive_daily_backup(None)
    assert result["via"] == "graph"
    assert len(uploaded) == 4
    assert "PMS-Decision-Platform/DailyEditBackup/Charts.xlsx" in uploaded


def test_maybe_skips_before_hour(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_enabled",
        True,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_hour_ist",
        19,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.daily_edit_dir",
        tmp_path,
    )
    monkeypatch.setattr(
        "pms_platform.jobs.onedrive_daily_backup.settings.onedrive_backup_dir",
        tmp_path / "DailyEditBackup",
    )

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 10, 18, 30, tzinfo=tz)

    monkeypatch.setattr("pms_platform.jobs.onedrive_daily_backup.datetime", _Fixed)
    assert maybe_run_onedrive_daily_backup(None) is None
