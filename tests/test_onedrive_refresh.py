"""Tests for Research/OneDrive sync into data/raw (no full DB reimport)."""

from pathlib import Path

from pms_platform.ingestion.onedrive_refresh import (
    _refresh_nse_bhav_best_effort,
    sync_raw_from_onedrive,
)
from pms_platform.market_data.nse_bhav_fetch import BhavFetchError
from pms_platform.research_paths import research_dir


def test_sync_raw_from_onedrive_copies_into_tmp(tmp_path: Path, monkeypatch) -> None:
    assert research_dir() is not None
    monkeypatch.setattr(
        "pms_platform.ingestion.onedrive_refresh.settings.raw_data_dir",
        tmp_path,
    )
    result = sync_raw_from_onedrive(raw_dir=tmp_path)
    assert (tmp_path / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx").is_file()
    assert (tmp_path / "security_master" / "SECURITY_MASTER_V1.xlsx").is_file()
    assert result.snapshot_count > 0
    assert any((tmp_path / "portfolio_snapshots").glob("Portfolio_*.xlsx"))


def test_refresh_nse_bhav_best_effort_records_skip(session, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise BhavFetchError("not published")

    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_fetch.fetch_and_commit_cm_udiff_bhav",
        _boom,
    )
    notes = _refresh_nse_bhav_best_effort(session)
    assert notes and "NSE bhav skipped" in notes[0]


def test_refresh_nse_bhav_best_effort_records_ok(session, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_fetch.fetch_and_commit_cm_udiff_bhav",
        lambda *_a, **_k: {"message": "Committed 2026-08-25: 1 rows (1 EQ)."},
    )
    notes = _refresh_nse_bhav_best_effort(session)
    assert notes == ["NSE bhav: Committed 2026-08-25: 1 rows (1 EQ)."]
