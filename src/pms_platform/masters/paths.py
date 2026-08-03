"""Resolve Final Master workbook paths (mirrors sync_raw_from_onedrive.sh)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pms_platform.config import settings
from pms_platform.research_paths import prefer_newest_existing, research_portfolio_dir


class MasterKind(StrEnum):
    SECURITY = "security"
    TRANSACTIONS = "transactions"
    SELL_SINCE = "sell_since"


_TXN_CANDIDATES = (
    "TRANSACTIONS_MASTER_V5_HARD_RECON_FIXES.xlsx",
    "TRANSACTIONS_MASTER_V3_2012_RECONCILIATION_POLICY.xlsx",
    "TRANSACTIONS_MASTER_V2_PRE2021_CORPORATE_ACTIONS.xlsx",
    "TRANSACTIONS_MASTER_V2.xlsx",
    "TRANSACTIONS_MASTER_V1.xlsx",
)

_DEFAULT_SHEETS = {
    MasterKind.SECURITY: "Security Master",
    MasterKind.TRANSACTIONS: "Sheet1",
    MasterKind.SELL_SINCE: "Sheet1",
}


@dataclass(frozen=True)
class MasterWorkbookInfo:
    kind: MasterKind
    label: str
    path: Path
    exists: bool
    default_sheet: str
    mtime: str | None
    size_bytes: int | None
    raw_sync_path: Path | None


def final_master_dir() -> Path:
    configured = settings.final_master_dir
    if configured is not None:
        return Path(configured).expanduser().resolve()
    # Default: sibling of the app package root's parent (…/PMS-Decision-Platform/02_Final_Master)
    # settings paths are relative to cwd (pms-decision-platform/).
    return (Path.cwd().resolve().parent / "02_Final_Master").resolve()


def resolve_transactions_path(master_dir: Path | None = None) -> Path:
    root = master_dir or final_master_dir()
    research_portfolio = research_portfolio_dir()
    for name in _TXN_CANDIDATES:
        candidates: list[Path] = []
        if research_portfolio is not None:
            candidates.append(research_portfolio / name)
        candidates.append(root / name)
        chosen = prefer_newest_existing(*candidates)
        if chosen is not None:
            return chosen
    return root / _TXN_CANDIDATES[-1]


def resolve_master_path(kind: MasterKind, master_dir: Path | None = None) -> Path:
    root = master_dir or final_master_dir()
    research_portfolio = research_portfolio_dir()
    if kind == MasterKind.SECURITY:
        research_sec = (
            prefer_newest_existing(
                research_portfolio / "SECURITY_MASTER_V1.xlsx",
            )
            if research_portfolio is not None
            else None
        )
        return research_sec or (root / "SECURITY_MASTER_V1.xlsx")
    if kind == MasterKind.TRANSACTIONS:
        return resolve_transactions_path(root)
    if kind == MasterKind.SELL_SINCE:
        research_sell = (
            prefer_newest_existing(
                research_portfolio / "Sellsince2012.xlsx",
                research_portfolio / "Sell_Since_Completed_All_Missing_Stocks.xlsx",
            )
            if research_portfolio is not None
            else None
        )
        return research_sell or (root / "Sell_Since_Completed_All_Missing_Stocks.xlsx")
    msg = f"Unknown master kind: {kind}"
    raise ValueError(msg)


def raw_sync_target(kind: MasterKind) -> Path | None:
    raw = Path(settings.raw_data_dir)
    if kind == MasterKind.SECURITY:
        return raw / "security_master" / "SECURITY_MASTER_V1.xlsx"
    if kind == MasterKind.TRANSACTIONS:
        return raw / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx"
    return None


def default_sheet(kind: MasterKind) -> str:
    return _DEFAULT_SHEETS[kind]


def workbook_info(kind: MasterKind, master_dir: Path | None = None) -> MasterWorkbookInfo:
    path = resolve_master_path(kind, master_dir)
    labels = {
        MasterKind.SECURITY: "Security Master",
        MasterKind.TRANSACTIONS: "Transactions Master",
        MasterKind.SELL_SINCE: "Sell Since",
    }
    exists = path.is_file()
    mtime = None
    size = None
    if exists:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        size = stat.st_size
    return MasterWorkbookInfo(
        kind=kind,
        label=labels[kind],
        path=path,
        exists=exists,
        default_sheet=default_sheet(kind),
        mtime=mtime,
        size_bytes=size,
        raw_sync_path=raw_sync_target(kind),
    )


def list_workbooks(master_dir: Path | None = None) -> list[MasterWorkbookInfo]:
    return [workbook_info(kind, master_dir) for kind in MasterKind]
