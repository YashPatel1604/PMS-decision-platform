"""Tests for Research knowledge-base path resolution."""

from pathlib import Path
from unittest.mock import patch

from pms_platform.research_paths import (
    default_portfolio_snapshots_dir,
    prefer_newest_existing,
    research_dir,
    research_portfolio_dir,
    research_portfolio_history_dir,
    research_portfolio_yearly_dir,
)


def test_research_dir_auto_detects_sibling_onedrive() -> None:
    root = research_dir()
    assert root is not None
    assert root.name == "Research"
    assert root.is_dir()


def test_research_portfolio_dirs_exist() -> None:
    portfolio = research_portfolio_dir()
    assert portfolio is not None
    assert portfolio.is_dir()
    yearly = research_portfolio_yearly_dir()
    assert yearly is not None
    assert any(yearly.glob("Portfolio_*.xlsx"))


def test_default_portfolio_snapshots_prefers_research() -> None:
    snapshots = default_portfolio_snapshots_dir()
    assert "Research" in snapshots.parts
    assert any(snapshots.glob("Portfolio_*.xlsx"))


def test_prefer_newest_existing(tmp_path: Path) -> None:
    older = tmp_path / "older.xlsx"
    newer = tmp_path / "newer.xlsx"
    older.write_text("a", encoding="utf-8")
    newer.write_text("b", encoding="utf-8")
    import os

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))
    chosen = prefer_newest_existing(older, newer, tmp_path / "missing.xlsx")
    assert chosen == newer


def test_research_dir_accepts_portfolio_path(tmp_path: Path) -> None:
    research = tmp_path / "Research"
    portfolio = research / "Portfolio"
    history = portfolio / "History"
    history.mkdir(parents=True)
    (history / "PMS_ClientPortfolio_311225.xlsx").write_text("x", encoding="utf-8")

    with patch("pms_platform.research_paths.settings") as mock_settings:
        mock_settings.research_dir = portfolio
        mock_settings.snapshot_seed_dir = None
        mock_settings.raw_data_dir = tmp_path / "raw"
        assert research_dir() == research
        assert research_portfolio_dir() == portfolio
        assert research_portfolio_history_dir() == history


def test_history_dir_case_insensitive(tmp_path: Path) -> None:
    research = tmp_path / "Research"
    portfolio = research / "Portfolio"
    history = portfolio / "history"
    history.mkdir(parents=True)

    with patch("pms_platform.research_paths.settings") as mock_settings:
        mock_settings.research_dir = research
        found = research_portfolio_history_dir()
        assert found is not None
        assert found.is_dir()
        assert found.name.lower() == "history"
