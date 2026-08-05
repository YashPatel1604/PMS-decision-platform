"""Resolve the sibling OneDrive Research knowledge-base paths.

Research is read-only authoritative portfolio data. The app may read from it
and copy into data/raw; it must never write back into Research.

``RESEARCH_DIR`` may point at either:
- ``…/Research`` (preferred — contains ``Portfolio/``), or
- ``…/Research/Portfolio`` (also accepted; History lives here as ``History/``).
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


def _looks_like_portfolio_dir(path: Path) -> bool:
    """True when path is Research/Portfolio (History / Yearly / Values live here)."""
    if not path.is_dir():
        return False
    markers = (
        path / "History",
        path / "Portfolio Yearly",
        path / "Values.xlsx",
    )
    if any(marker.exists() for marker in markers):
        return True
    # Case-insensitive History on Windows mounts
    try:
        names = {child.name.lower() for child in path.iterdir()}
    except OSError:
        return False
    return "history" in names or "portfolio yearly" in names


def _child_dir_ci(parent: Path, name: str) -> Path | None:
    """Return parent/name if present, matching case-insensitively when needed."""
    direct = parent / name
    if direct.is_dir():
        return direct
    try:
        for child in parent.iterdir():
            if child.is_dir() and child.name.lower() == name.lower():
                return child
    except OSError:
        return None
    return None


def research_dir() -> Path | None:
    """Return configured or auto-detected Research directory if it exists.

    If ``RESEARCH_DIR`` points at the Portfolio folder itself, return its parent
    when that parent is named Research; otherwise still treat Portfolio as usable
    via ``research_portfolio_dir``.
    """
    configured = settings.research_dir
    if configured is not None:
        path = Path(configured).expanduser().resolve()
        if not path.is_dir():
            return None
        # User pointed at …/Research/Portfolio — Research root is parent.
        if _looks_like_portfolio_dir(path):
            parent = path.parent
            if parent.is_dir():
                return parent
            return path
        return path

    candidate = _onedrive_personal_root() / "Research"
    return candidate if candidate.is_dir() else None


def research_portfolio_dir() -> Path | None:
    """Return Research/Portfolio when present (or RESEARCH_DIR if it is Portfolio)."""
    configured = settings.research_dir
    if configured is not None:
        path = Path(configured).expanduser().resolve()
        if _looks_like_portfolio_dir(path):
            return path

    root = research_dir()
    if root is None:
        return None
    if _looks_like_portfolio_dir(root):
        return root
    return _child_dir_ci(root, "Portfolio")


def research_portfolio_yearly_dir() -> Path | None:
    """Return Research/Portfolio/Portfolio Yearly when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    return _child_dir_ci(portfolio, "Portfolio Yearly")


def research_portfolio_history_dir() -> Path | None:
    """Return Research/Portfolio/History when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    return _child_dir_ci(portfolio, "History")


def research_values_workbook() -> Path | None:
    """Return Research/Portfolio/Values.xlsx when present."""
    portfolio = research_portfolio_dir()
    if portfolio is None:
        return None
    path = portfolio / "Values.xlsx"
    if path.is_file():
        return path
    try:
        for child in portfolio.iterdir():
            if child.is_file() and child.name.lower() == "values.xlsx":
                return child
    except OSError:
        return None
    return None


def prefer_newest_existing(*candidates: Path) -> Path | None:
    """Pick the newest existing file among candidates (by mtime)."""
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def describe_research_layout() -> dict[str, object]:
    """Diagnostic snapshot of what the process can see under RESEARCH_DIR."""
    configured = str(settings.research_dir) if settings.research_dir else None
    root = research_dir()
    portfolio = research_portfolio_dir()
    history = research_portfolio_history_dir()
    yearly = research_portfolio_yearly_dir()
    portfolio_children: list[str] = []
    if portfolio is not None:
        try:
            portfolio_children = sorted(child.name for child in portfolio.iterdir())[:40]
        except OSError as exc:
            portfolio_children = [f"<error: {exc}>"]
    history_count = 0
    if history is not None:
        try:
            history_count = sum(
                1
                for p in history.iterdir()
                if p.is_file() and p.name.lower().startswith("pms_clientportfolio_")
            )
        except OSError:
            history_count = -1
    return {
        "configured_research_dir": configured,
        "resolved_research_dir": str(root) if root else None,
        "resolved_portfolio_dir": str(portfolio) if portfolio else None,
        "resolved_history_dir": str(history) if history else None,
        "resolved_yearly_dir": str(yearly) if yearly else None,
        "portfolio_children": portfolio_children,
        "history_file_count": history_count,
        "values_xlsx": str(research_values_workbook()) if research_values_workbook() else None,
    }


def portfolio_snapshot_source_dirs() -> list[Path]:
    """Directories to read Portfolio_*.xlsx from, Research first.

    Order: Research/Portfolio Yearly, Research/Portfolio root, snapshot seed
    (Docker fallback), then legacy OneDrive originals under the project tree.
    """
    dirs: list[Path] = []
    yearly = research_portfolio_yearly_dir()
    if yearly is not None:
        dirs.append(yearly)
    portfolio = research_portfolio_dir()
    if portfolio is not None:
        dirs.append(portfolio)

    seed = settings.snapshot_seed_dir
    if seed is not None:
        seed_path = Path(seed).expanduser().resolve()
        if seed_path.is_dir():
            dirs.append(seed_path)
    else:
        for candidate in (
            Path("/data/snapshot_seed"),
            Path("docker/portfolio_snapshot_seed"),
        ):
            if candidate.is_dir():
                dirs.append(candidate.resolve())
                break

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
