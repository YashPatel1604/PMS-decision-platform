"""Catalog Research/Portfolio workbooks: roles, readability, and usage priority.

OneDrive Files On-Demand often leaves cloud-only placeholders that Docker cannot
read. This module inventories expected assets and reports which are usable so
Refresh / Holdings can explain partial data instead of silently skipping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pms_platform.research_paths import (
    research_dir,
    research_portfolio_dir,
    research_portfolio_history_dir,
    research_portfolio_yearly_dir,
    research_values_workbook,
)


class ResearchAssetRole(StrEnum):
    """How the platform uses a Research asset today."""

    REQUIRED_REFRESH = "required_refresh"
    RUNTIME_LOOKUP = "runtime_lookup"
    OPTIONAL_MASTER = "optional_master"
    NOT_INGESTED = "not_ingested"
    IGNORE = "ignore"


@dataclass(frozen=True)
class ResearchAssetSpec:
    """One expected Research path pattern."""

    key: str
    label: str
    role: ResearchAssetRole
    description: str
    # Relative to Research/Portfolio unless absolute_glob is set under Portfolio.
    relative_path: str | None = None
    # Glob under Portfolio (e.g. Portfolio Yearly/Portfolio_*.xlsx).
    relative_glob: str | None = None


# Authoritative map: what each Portfolio file/folder is for.
_PORTFOLIO_SPECS: tuple[ResearchAssetSpec, ...] = (
    ResearchAssetSpec(
        key="portfolio_yearly",
        label="Portfolio Yearly snapshots",
        role=ResearchAssetRole.REQUIRED_REFRESH,
        description="Annual Portfolio_YYYY.xlsx books — quantities used for snapshot import.",
        relative_glob="Portfolio Yearly/Portfolio_*.xlsx",
    ),
    ResearchAssetSpec(
        key="portfolio_root_snapshots",
        label="Root Portfolio_*.xlsx",
        role=ResearchAssetRole.REQUIRED_REFRESH,
        description="Current-year (or extra) snapshot workbooks in Portfolio root.",
        relative_glob="Portfolio_*.xlsx",
    ),
    ResearchAssetSpec(
        key="history",
        label="History (PMS_ClientPortfolio_*)",
        role=ResearchAssetRole.RUNTIME_LOOKUP,
        description="Authoritative portfolio totals for Holdings From/To dates.",
        relative_path="History",
    ),
    ResearchAssetSpec(
        key="values",
        label="Values.xlsx",
        role=ResearchAssetRole.RUNTIME_LOOKUP,
        description="Date → portfolio value fallback when History has no exact date.",
        relative_path="Values.xlsx",
    ),
    ResearchAssetSpec(
        key="sell_since",
        label="Sellsince2012.xlsx",
        role=ResearchAssetRole.OPTIONAL_MASTER,
        description="Sell-since master for Masters UI / calibration.",
        relative_path="Sellsince2012.xlsx",
    ),
    ResearchAssetSpec(
        key="bse500_from2012",
        label="BSE500TRI_From2012.xlsx",
        role=ResearchAssetRole.OPTIONAL_MASTER,
        description="BSE 500 TRI history — used when importing benchmark market data.",
        relative_path="BSE500TRI_From2012.xlsx",
    ),
    ResearchAssetSpec(
        key="bse500_xls",
        label="BSE500TRI.xls",
        role=ResearchAssetRole.OPTIONAL_MASTER,
        description="Legacy BSE 500 TRI workbook (xls).",
        relative_path="BSE500TRI.xls",
    ),
    ResearchAssetSpec(
        key="txn_research",
        label="StockTransactionSince2012*.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description=(
            "Legacy/research transaction extracts. Platform refresh uses "
            "TRANSACTIONS_MASTER_* from Final Master seed (or Research if present)."
        ),
        relative_glob="StockTransactionSince2012*.xlsx",
    ),
    ResearchAssetSpec(
        key="pms_client_live",
        label="PMS_ClientPortfolio.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Live client portfolio workbook — not yet wired as import source.",
        relative_path="PMS_ClientPortfolio.xlsx",
    ),
    ResearchAssetSpec(
        key="cagr",
        label="CAGR_PMS.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Performance/CAGR research sheet — not auto-imported.",
        relative_path="CAGR_PMS.xlsx",
    ),
    ResearchAssetSpec(
        key="performance_monthly",
        label="Performance_SavvyCapitalMonthly.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Monthly performance research — not auto-imported.",
        relative_path="Performance_SavvyCapitalMonthly.xlsx",
    ),
    ResearchAssetSpec(
        key="fair_value_portfolio",
        label="Stocks_FairValue_Portfolio.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Fair-value portfolio research — not auto-imported.",
        relative_path="Stocks_FairValue_Portfolio.xlsx",
    ),
    ResearchAssetSpec(
        key="fair_value_watchlist",
        label="Stocks_FairValue_Watchlist.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Fair-value watchlist research — seed with `pms-platform seed-watchlist`.",
        relative_path="Stocks_FairValue_Watchlist.xlsx",
    ),
    ResearchAssetSpec(
        key="positional_watch",
        label="PositionalWatch.xlsx",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Positional watch research — not auto-imported.",
        relative_path="PositionalWatch.xlsx",
    ),
    ResearchAssetSpec(
        key="target_aum",
        label="TargetAUM.xls",
        role=ResearchAssetRole.NOT_INGESTED,
        description="Target AUM notes — not auto-imported.",
        relative_path="TargetAUM.xls",
    ),
    ResearchAssetSpec(
        key="docs",
        label="Word notes (.docx)",
        role=ResearchAssetRole.IGNORE,
        description="Narrative notes only — not used by the decision platform.",
        relative_glob="*.docx",
    ),
    ResearchAssetSpec(
        key="companies",
        label="Companies/",
        role=ResearchAssetRole.IGNORE,
        description="Per-company research folders — not part of portfolio refresh.",
        relative_path="Companies",
    ),
)


@dataclass
class ResearchAssetStatus:
    key: str
    label: str
    role: str
    description: str
    expected_path: str | None
    present: bool
    readable: bool
    item_count: int
    size_bytes: int | None
    note: str | None = None


@dataclass
class ResearchInventory:
    research_dir: str | None
    portfolio_dir: str | None
    assets: list[ResearchAssetStatus] = field(default_factory=list)
    required_ok: bool = False
    runtime_ok: bool = False
    missing_required: list[str] = field(default_factory=list)
    missing_runtime: list[str] = field(default_factory=list)
    guidance: list[str] = field(default_factory=list)


def _is_probably_cloud_placeholder(path: Path) -> bool:
    """Heuristic: zero-byte or tiny OneDrive placeholder files."""
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if path.is_file() and size == 0:
        return True
    return False


def _path_readable(path: Path) -> tuple[bool, int | None, str | None]:
    if not path.exists():
        return False, None, "missing"
    try:
        if path.is_dir():
            # Directory "readable" if we can list and see at least one non-placeholder child
            # for History, or any child for other dirs.
            children = list(path.iterdir())
            usable = [
                c
                for c in children
                if c.name != ".DS_Store" and not (c.is_file() and _is_probably_cloud_placeholder(c))
            ]
            if not usable:
                return False, None, "folder empty or all cloud-only placeholders"
            return True, None, None
        if _is_probably_cloud_placeholder(path):
            return False, 0, "cloud-only / zero-byte placeholder — pin Always keep on this device"
        size = path.stat().st_size
        # Touch-open for xlsx/xls to catch dehydrated files that report a size but fail.
        if path.suffix.lower() in {".xlsx", ".xls"}:
            with path.open("rb") as handle:
                handle.read(64)
        return True, size, None
    except OSError as exc:
        return False, None, f"not readable ({exc})"


def _resolve_matches(portfolio: Path, spec: ResearchAssetSpec) -> list[Path]:
    if spec.relative_path is not None:
        path = portfolio / spec.relative_path
        return [path] if path.exists() else [path]
    if spec.relative_glob is not None:
        matches = sorted(portfolio.glob(spec.relative_glob))
        return matches
    return []


def build_research_inventory() -> ResearchInventory:
    """Scan Research/Portfolio against the known asset map."""
    root = research_dir()
    portfolio = research_portfolio_dir()
    inventory = ResearchInventory(
        research_dir=str(root) if root else None,
        portfolio_dir=str(portfolio) if portfolio else None,
    )

    if portfolio is None:
        inventory.guidance.append(
            "RESEARCH_DIR must point at the Research folder that contains Portfolio/. "
            "On Windows OneDrive, mark Research\\Portfolio Always keep on this device."
        )
        inventory.missing_required = ["portfolio_yearly", "portfolio_root_snapshots"]
        return inventory

    for spec in _PORTFOLIO_SPECS:
        matches = _resolve_matches(portfolio, spec)
        if spec.relative_glob is not None:
            readable_matches: list[Path] = []
            total_size = 0
            notes: list[str] = []
            for match in matches:
                ok, size, note = _path_readable(match)
                if ok:
                    readable_matches.append(match)
                    if size:
                        total_size += size
                elif note:
                    notes.append(f"{match.name}: {note}")
            present = len(matches) > 0
            readable = len(readable_matches) > 0
            # Required snapshot roles: need at least one readable Portfolio_*.xlsx across yearly+root.
            status = ResearchAssetStatus(
                key=spec.key,
                label=spec.label,
                role=spec.role.value,
                description=spec.description,
                expected_path=str(portfolio / (spec.relative_glob or "")),
                present=present,
                readable=readable,
                item_count=len(readable_matches),
                size_bytes=total_size or None,
                note="; ".join(notes[:3]) if notes else (
                    None if readable else "no readable matches"
                ),
            )
        else:
            path = matches[0] if matches else portfolio / (spec.relative_path or spec.key)
            ok, size, note = _path_readable(path)
            # History: also count PMS_ClientPortfolio_* files
            item_count = 0
            if path.is_dir() and ok:
                item_count = len(
                    [
                        p
                        for p in path.glob("PMS_ClientPortfolio_*")
                        if p.is_file() and not _is_probably_cloud_placeholder(p)
                    ]
                )
                if spec.key == "history" and item_count == 0:
                    ok = False
                    note = "History folder has no readable PMS_ClientPortfolio_* files"
            status = ResearchAssetStatus(
                key=spec.key,
                label=spec.label,
                role=spec.role.value,
                description=spec.description,
                expected_path=str(path),
                present=path.exists(),
                readable=ok,
                item_count=item_count if path.is_dir() else (1 if ok else 0),
                size_bytes=size,
                note=note,
            )
        inventory.assets.append(status)

    # Snapshot requirement: yearly OR root must have readable Portfolio_*.xlsx
    yearly = next((a for a in inventory.assets if a.key == "portfolio_yearly"), None)
    root_snaps = next((a for a in inventory.assets if a.key == "portfolio_root_snapshots"), None)
    snapshots_ok = bool((yearly and yearly.readable) or (root_snaps and root_snaps.readable))

    required = [a for a in inventory.assets if a.role == ResearchAssetRole.REQUIRED_REFRESH.value]
    # Only flag missing required if neither snapshot source works
    inventory.missing_required = []
    if not snapshots_ok:
        inventory.missing_required.append("Portfolio_*.xlsx (Portfolio Yearly or Portfolio root)")
    inventory.required_ok = snapshots_ok

    runtime = [a for a in inventory.assets if a.role == ResearchAssetRole.RUNTIME_LOOKUP.value]
    inventory.missing_runtime = [a.label for a in runtime if not a.readable]
    inventory.runtime_ok = len(inventory.missing_runtime) == 0

    if not inventory.required_ok:
        inventory.guidance.append(
            "Pin Research\\Portfolio and Research\\Portfolio\\Portfolio Yearly as "
            "Always keep on this device, wait for green checkmarks (not cloud icons), "
            "then restart Docker and Refresh."
        )
    if inventory.missing_runtime:
        inventory.guidance.append(
            "Holdings portfolio totals need History/ and Values.xlsx local. "
            f"Missing or unreadable: {', '.join(inventory.missing_runtime)}."
        )
    # Confirm helpers used elsewhere still resolve
    if research_portfolio_yearly_dir() is None and research_values_workbook() is None:
        pass
    if research_portfolio_history_dir() is None:
        inventory.guidance.append("History/ folder not found under Research/Portfolio.")

    inventory.guidance.append(
        "Refresh imports: Portfolio_*.xlsx snapshots + transaction/security masters. "
        "Holdings totals read History/Values at runtime. Other Portfolio Excel "
        "(fair value, CAGR, StockTransaction…) is catalogued but not auto-imported yet."
    )
    return inventory
