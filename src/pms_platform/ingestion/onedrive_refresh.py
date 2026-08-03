"""Sync Research/OneDrive masters into data/raw and fully reimport."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pms_platform.analytics.research_portfolio_value import clear_research_portfolio_value_cache
from pms_platform.config import settings
from pms_platform.episodes.builder import build_episodes
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import clear_portfolio_snapshots, import_portfolio_snapshots
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data
from pms_platform.masters.paths import final_master_dir, resolve_master_path, MasterKind
from pms_platform.models import (
    DecisionEvent,
    EpisodeCashFlowRecord,
    EpisodePerformance,
    ImportBatch,
    InvestmentEpisode,
    LiquidTransaction,
    PostExitHorizonPerformance,
    PostExitPerformance,
    Security,
    SellAssessment,
    Transaction,
)
from pms_platform.research_paths import (
    portfolio_snapshot_source_dirs,
    research_dir,
    research_portfolio_dir,
)


@dataclass
class SyncRawResult:
    copied: list[str] = field(default_factory=list)
    snapshot_count: int = 0
    research_dir: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ReimportResult:
    securities_inserted: int = 0
    equity_txns_inserted: int = 0
    liquid_txns_inserted: int = 0
    episodes: int = 0
    decision_events: int = 0
    snapshots_inserted: int = 0
    snapshots_unresolved: int = 0
    validation_errors: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class OnedriveRefreshResult:
    sync: SyncRawResult
    reimport: ReimportResult | None = None
    ok: bool = True
    error: str | None = None


def _copy_ro(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.chmod(0o644)
    shutil.copy2(src, dest)
    dest.chmod(0o444)


def sync_raw_from_onedrive(*, raw_dir: Path | None = None) -> SyncRawResult:
    """Copy Research / Final Master workbooks into data/raw (read-only copies)."""
    raw = Path(raw_dir or settings.raw_data_dir)
    result = SyncRawResult(research_dir=str(research_dir()) if research_dir() else None)

    txn_src = resolve_master_path(MasterKind.TRANSACTIONS)
    sec_src = resolve_master_path(MasterKind.SECURITY)
    if not txn_src.is_file():
        msg = f"Missing transactions master: {txn_src}"
        raise FileNotFoundError(msg)
    if not sec_src.is_file():
        # Fall back to Final Master explicitly if Research path resolution missed it.
        legacy = final_master_dir() / "SECURITY_MASTER_V1.xlsx"
        if legacy.is_file():
            sec_src = legacy
        else:
            msg = f"Missing security master: {sec_src}"
            raise FileNotFoundError(msg)

    txn_dest = raw / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx"
    sec_dest = raw / "security_master" / "SECURITY_MASTER_V1.xlsx"
    _copy_ro(txn_src, txn_dest)
    result.copied.append(f"{txn_dest.name} ← {txn_src}")
    _copy_ro(sec_src, sec_dest)
    result.copied.append(f"{sec_dest.name} ← {sec_src}")

    snap_dest_dir = raw / "portfolio_snapshots"
    snap_dest_dir.mkdir(parents=True, exist_ok=True)
    for old in snap_dest_dir.glob("Portfolio_*.xlsx"):
        old.chmod(0o644)
        old.unlink()

    seen: set[str] = set()
    source_dirs = portfolio_snapshot_source_dirs()
    for directory in source_dirs:
        for src in sorted(directory.glob("Portfolio_*.xlsx")):
            if src.name.startswith("~$"):
                continue
            if src.name in seen:
                continue
            dest = snap_dest_dir / src.name
            _copy_ro(src, dest)
            seen.add(src.name)
            result.copied.append(f"{src.name} ← {src}")
            result.snapshot_count += 1

    if result.snapshot_count == 0:
        checked = ", ".join(str(d) for d in source_dirs) or "(no source dirs found)"
        research = research_dir()
        portfolio = research_portfolio_dir()
        detail = (
            f"No Portfolio_*.xlsx snapshot workbooks found. "
            f"Checked: {checked}. "
            f"research_dir={research!s}; portfolio_dir={portfolio!s}. "
            "On Windows: set RESEARCH_DIR to the Research folder that contains "
            "Portfolio/, mark Portfolio (and Portfolio Yearly) Always keep on this "
            "device, then restart containers. Or rely on docker/portfolio_snapshot_seed."
        )
        result.notes.append(detail)
        raise FileNotFoundError(detail)
    result.notes.append(f"Synced {result.snapshot_count} portfolio snapshot workbook(s)")

    portfolio = research_portfolio_dir()
    if portfolio is not None:
        result.notes.append(f"Research portfolio root: {portfolio}")
    return result


def reimport_from_raw(session: Session, *, raw_dir: Path | None = None) -> ReimportResult:
    """Wipe checksum-gated imports and reload securities/transactions/snapshots/episodes."""
    raw = Path(raw_dir or settings.raw_data_dir)
    security_path = raw / "security_master" / "SECURITY_MASTER_V1.xlsx"
    transaction_path = raw / "transactions" / "MASTER_TRANSACTIONS_V1.xlsx"
    snapshot_dir = raw / "portfolio_snapshots"

    if not security_path.is_file():
        raise FileNotFoundError(f"Missing {security_path}")
    if not transaction_path.is_file():
        raise FileNotFoundError(f"Missing {transaction_path}")

    session.execute(delete(PostExitHorizonPerformance))
    session.execute(delete(PostExitPerformance))
    session.execute(delete(SellAssessment))
    session.execute(delete(EpisodePerformance))
    session.execute(delete(EpisodeCashFlowRecord))
    session.execute(delete(DecisionEvent))
    session.execute(delete(InvestmentEpisode))
    session.execute(delete(Transaction))
    session.execute(delete(LiquidTransaction))
    clear_portfolio_snapshots(session)
    # Keep Security rows so daily_prices / dividends / symbol history stay attached;
    # import_security_master upserts master fields from the workbook.
    session.execute(
        delete(ImportBatch).where(
            ImportBatch.source_type.in_(["transactions", "securities", "snapshots"])
        )
    )
    session.flush()

    sec = import_security_master(session, security_path)
    txn = import_transaction_master(session, transaction_path)
    issues = validate_imported_data(session)
    errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
    if errors:
        session.commit()
        return ReimportResult(
            securities_inserted=sec.inserted,
            equity_txns_inserted=txn.equity_inserted,
            liquid_txns_inserted=txn.liquid_inserted,
            validation_errors=len(errors),
            notes=[f"Validation failed with {len(errors)} error(s)"],
        )

    episodes, decisions = build_episodes(session)
    snap = import_portfolio_snapshots(session, snapshot_dir)
    session.commit()
    clear_research_portfolio_value_cache()

    return ReimportResult(
        securities_inserted=sec.inserted,
        equity_txns_inserted=txn.equity_inserted,
        liquid_txns_inserted=txn.liquid_inserted,
        episodes=len(episodes),
        decision_events=len(decisions),
        snapshots_inserted=snap.inserted,
        snapshots_unresolved=snap.unresolved_names,
        validation_errors=0,
        notes=["Reimport complete"],
    )


def refresh_from_onedrive(session: Session) -> OnedriveRefreshResult:
    """Sync Research/OneDrive → data/raw, then full reimport."""
    try:
        sync = sync_raw_from_onedrive()
    except Exception as exc:  # noqa: BLE001
        return OnedriveRefreshResult(
            sync=SyncRawResult(notes=[str(exc)]),
            ok=False,
            error=f"Sync failed: {exc}",
        )
    try:
        reimport = reimport_from_raw(session)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        return OnedriveRefreshResult(
            sync=sync,
            ok=False,
            error=f"Reimport failed: {exc}",
        )
    ok = reimport.validation_errors == 0
    return OnedriveRefreshResult(
        sync=sync,
        reimport=reimport,
        ok=ok,
        error=None if ok else "Validation errors during reimport",
    )
