"""Sync Research/OneDrive sources into DB through one pipeline.

Pipeline steps:
1) Sync masters/snapshots from Research into data/raw
2) Reimport portfolio data into Postgres
3) Import market-data CSVs (prefer OneDrive external path over seed)
4) Recompute episode analysis
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pms_platform.analytics.research_portfolio_value import clear_research_portfolio_value_cache
from pms_platform.analytics.service import run_full_episode_analysis
from pms_platform.config import settings
from pms_platform.episodes.builder import build_episodes
from pms_platform.episodes.model_reconcile import reconcile_open_episodes_to_client_model
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import clear_portfolio_snapshots, import_portfolio_snapshots
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.ingestion.validators import ValidationSeverity, validate_imported_data
from pms_platform.market_data.client_portfolio_parse import clear_client_portfolio_cache
from pms_platform.market_data.contracts import CanonicalPaths
from pms_platform.market_data.importer import import_market_data
from pms_platform.masters.paths import MasterKind, final_master_dir, resolve_master_path
from pms_platform.models import (
    DecisionEvent,
    EpisodeCashFlowRecord,
    EpisodePerformance,
    ImportBatch,
    InvestmentEpisode,
    LiquidTransaction,
    PostExitHorizonPerformance,
    PostExitPerformance,
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
class MarketDataRefreshResult:
    source_dir: str
    used_seed_fallback: bool
    missing_files: list[str] = field(default_factory=list)
    prices_inserted: int = 0
    prices_skipped: int = 0
    prices_unresolved: int = 0
    prices_invalid: int = 0
    dividends_inserted: int = 0
    dividends_skipped: int = 0
    dividends_unresolved: int = 0
    dividends_invalid: int = 0
    benchmarks_inserted: int = 0
    benchmarks_skipped: int = 0
    benchmarks_invalid: int = 0
    successors_inserted: int = 0
    successors_skipped: int = 0
    successors_invalid: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisRefreshResult:
    ownership_ok: int = 0
    ownership_insufficient: int = 0
    post_exit_ok: int = 0
    post_exit_insufficient: int = 0
    cash_flow_rows: int = 0


@dataclass
class OnedriveRefreshResult:
    sync: SyncRawResult
    reimport: ReimportResult | None = None
    market_data: MarketDataRefreshResult | None = None
    analysis: AnalysisRefreshResult | None = None
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
    model_closed = reconcile_open_episodes_to_client_model(session)
    snap = import_portfolio_snapshots(session, snapshot_dir)
    session.commit()
    clear_research_portfolio_value_cache()
    clear_client_portfolio_cache()

    notes = ["Reimport complete"]
    if model_closed:
        names = ", ".join(row.portfolio_name for row in model_closed[:8])
        notes.append(
            f"Closed {len(model_closed)} episode(s) absent from Client Portfolio Model: {names}"
        )

    return ReimportResult(
        securities_inserted=sec.inserted,
        equity_txns_inserted=txn.equity_inserted,
        liquid_txns_inserted=txn.liquid_inserted,
        episodes=len(episodes),
        decision_events=len(decisions),
        snapshots_inserted=snap.inserted,
        snapshots_unresolved=snap.unresolved_names,
        validation_errors=0,
        notes=notes,
    )


def _has_any_market_csv(path: Path) -> bool:
    contract = CanonicalPaths()
    expected = (
        path / contract.prices,
        path / contract.dividends,
        path / contract.benchmarks,
        path / contract.successors,
    )
    return any(p.is_file() for p in expected)


def _resolve_market_data_source_dir() -> tuple[Path, bool]:
    """Prefer OneDrive external path when present; otherwise use seed fallback."""
    candidates = [
        Path(settings.external_data_dir),  # Compose points this to mounted external source.
        Path("/data/external"),  # Docker default mount path.
    ]
    seed = Path("/data/external_seed")

    for candidate in candidates:
        if candidate.is_dir() and _has_any_market_csv(candidate):
            return candidate, False
    if seed.is_dir() and _has_any_market_csv(seed):
        return seed, True
    # Fall back to configured dir for clearer missing-file diagnostics downstream.
    return Path(settings.external_data_dir), False


def import_market_and_analyze(session: Session) -> tuple[MarketDataRefreshResult, AnalysisRefreshResult]:
    source_dir, used_seed_fallback = _resolve_market_data_source_dir()
    market = import_market_data(session, source_dir)
    summary = run_full_episode_analysis(session)
    session.commit()

    return (
        MarketDataRefreshResult(
            source_dir=str(source_dir),
            used_seed_fallback=used_seed_fallback,
            missing_files=list(market.missing_files),
            prices_inserted=market.prices.inserted if market.prices else 0,
            prices_skipped=market.prices.skipped if market.prices else 0,
            prices_unresolved=market.prices.unresolved if market.prices else 0,
            prices_invalid=market.prices.invalid if market.prices else 0,
            dividends_inserted=market.dividends.inserted if market.dividends else 0,
            dividends_skipped=market.dividends.skipped if market.dividends else 0,
            dividends_unresolved=market.dividends.unresolved if market.dividends else 0,
            dividends_invalid=market.dividends.invalid if market.dividends else 0,
            benchmarks_inserted=market.benchmarks.inserted if market.benchmarks else 0,
            benchmarks_skipped=market.benchmarks.skipped if market.benchmarks else 0,
            benchmarks_invalid=market.benchmarks.invalid if market.benchmarks else 0,
            successors_inserted=market.successors.inserted if market.successors else 0,
            successors_skipped=market.successors.skipped if market.successors else 0,
            successors_invalid=market.successors.invalid if market.successors else 0,
            notes=(
                ["Used docker market-data seed fallback"]
                if used_seed_fallback
                else ["Used OneDrive-configured external market-data path"]
            ),
        ),
        AnalysisRefreshResult(
            ownership_ok=summary.ownership_ok,
            ownership_insufficient=summary.ownership_insufficient,
            post_exit_ok=summary.post_exit_ok,
            post_exit_insufficient=summary.post_exit_insufficient,
            cash_flow_rows=summary.cash_flow_rows,
        ),
    )


def refresh_from_onedrive(session: Session) -> OnedriveRefreshResult:
    """Full refresh: sync raw + reimport + market import + analysis."""
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

    if reimport.validation_errors:
        return OnedriveRefreshResult(
            sync=sync,
            reimport=reimport,
            ok=False,
            error="Validation errors during reimport",
        )

    try:
        market_data, analysis = import_market_and_analyze(session)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        return OnedriveRefreshResult(
            sync=sync,
            reimport=reimport,
            ok=False,
            error=f"Market-data import or analysis failed: {exc}",
        )

    return OnedriveRefreshResult(
        sync=sync,
        reimport=reimport,
        market_data=market_data,
        analysis=analysis,
        ok=True,
        error=None,
    )
