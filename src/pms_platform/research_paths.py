"""Resolve the sibling OneDrive Research knowledge-base paths.

Research is read-only authoritative portfolio data. The app may read from it
and copy into data/raw; it must never write back into Research.
"""

from __future__ import annotations

from pathlib import Path

from pms_platform.config import settings


def _onedrive_personal_root() -> Path:
    """Parent of PMS-Decision-Platform when cwd is the app package directory."""
    cwd = Path.cwd().resolve()
    # Typical: …/PMS-Decision-Platform/pms-decision-platform
    if cwd.name == "pms-decision-platform":
        return cwd.parent.parent
    # …/PMS-Decision-Platform
    if (cwd / "pms-decision-platform").is_dir() or (cwd / "02_Final_Master").is_dir():
        return cwd.parent
    return cwd.parent


def research_dir() -> Path | None:
    """Return configured or auto-detected Research directory if it exists."""
    configured = settings.research_dir
    if configured is not None:
        path = Path(configured).expanduser().resolve()
        return path if path.is_dir() else None

    candidate = _onedrive_personal_root() / "Research"
    return candidate if candidate.is_dir() else None


def research_portfolio_dir() -> Path | None:
    """Return Research/Portfolio when present."""
    root = research_dir()
    if root is None:
        return None
    portfolio = root / "Portfolio"
    return portfolio if portfolio.is_dir() else None


def research_portfolio_yearly_dir() -> Path | None:
    """Return Research/Portfolio/Portfolio Yearly when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    yearly = portfolio / "Portfolio Yearly"
    return yearly if yearly.is_dir() else None


def research_portfolio_history_dir() -> Path | None:
    """Return Research/Portfolio/History when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    history = portfolio / "History"
    return history if history.is_dir() else None


def research_values_workbook() -> Path | None:
    """Return Research/Portfolio/Values.xlsx when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    path = portfolio / "Values.xlsx"
    return path if path.is_file() else None


def prefer_newest_existing(*candidates: Path) -> Path | None:
    """Pick the newest existing file among candidates (by mtime)."""
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def portfolio_snapshot_source_dirs() -> list[Path]:
    """Directories to read Portfolio_*.xlsx from, Research first.

    Order: Research/Portfolio Yearly, Research/Portfolio root, then legacy
    OneDrive originals under the project tree.
    """
    dirs: list[Path] = []
    yearly = research_portfolio_yearly_dir()
    if yearly is not None:
        dirs.append(yearly)
    portfolio = research_portfolio_dir()
    if portfolio is not None:
        dirs.append(portfolio)

    cwd = Path.cwd().resolve()
    project_root = cwd.parent if cwd.name == "pms-decision-platform" else cwd
    legacy = project_root / "00_Original_Files" / "Portfolio_Snapshots"
    if legacy.is_dir():
        dirs.append(legacy)
    return dirs


def default_portfolio_snapshots_dir() -> Path:
    """Preferred directory for CLI snapshot import (Research Yearly or data/raw)."""
    yearly = research_portfolio_yearly_dir()
    if yearly is not None and any(yearly.glob("Portfolio_*.xlsx")):
        return yearly
    portfolio = research_portfolio_dir()
    if portfolio is not None and any(portfolio.glob("Portfolio_*.xlsx")):
        return portfolio
    return Path(settings.raw_data_dir) / "portfolio_snapshots"
