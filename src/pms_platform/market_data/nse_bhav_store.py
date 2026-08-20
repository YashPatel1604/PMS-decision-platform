"""Persist and query NSE bhav bars / import runs / portfolio symbols."""

from __future__ import annotations

import hashlib
import shutil
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.market_data.bhav_verify import (
    reconcile_day,
    validate_parsed_rows,
)
from pms_platform.market_data.nse_bhav_parse import (
    BhavParseError,
    ParsedBhavRow,
    parse_bhav_file,
)
from pms_platform.market_data.pivot_derived import (
    floor_pivots_for_symbols,
    volume_ranks,
)
from pms_platform.models.nse_bhav import (
    BhavImportRun,
    NseBhavBar,
    PivotPortfolioSymbol,
    PivotVolExp,
)

# Only this many trade sessions are kept; older days are deleted on each commit.
MAX_BHAV_SESSIONS = 20


def _bhav_upload_dir() -> Path:
    path = Path(settings.upload_dir) / "bhav"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_bhav_upload(session: Session, *, filename: str, content: bytes) -> BhavImportRun:
    """Write raw bytes to upload dir and create a staged run."""
    safe_name = Path(filename).name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = _bhav_upload_dir() / f"{stamp}_{safe_name}"
    dest.write_bytes(content)
    run = BhavImportRun(
        staged_path=str(dest.resolve()),
        source_filename=safe_name,
        source_checksum=_checksum(dest),
        status="staged",
        validation_report={},
        reconcile_report={},
    )
    session.add(run)
    session.flush()
    return run


def get_bhav_run(session: Session, run_id: int) -> BhavImportRun | None:
    return session.get(BhavImportRun, run_id)


def validate_bhav_run(session: Session, run_id: int) -> BhavImportRun:
    run = session.get(BhavImportRun, run_id)
    if run is None:
        raise LookupError(f"Unknown bhav run {run_id}")
    path = Path(run.staged_path)
    rows = parse_bhav_file(path)
    report = validate_parsed_rows(rows)
    run.trade_date = report.trade_date
    run.row_count_all = report.row_count_all
    run.row_count_eq = report.row_count_eq
    run.validation_report = report.as_dict()
    run.status = "validated" if report.ok else "failed"
    run.error_message = None if report.ok else "; ".join(report.errors[:5])
    session.flush()
    return run


def _replace_day_bars(
    session: Session,
    trade_date: date,
    rows: list[ParsedBhavRow],
    run_id: int,
) -> None:
    session.execute(delete(NseBhavBar).where(NseBhavBar.trade_date == trade_date))
    session.flush()
    for row in rows:
        session.add(
            NseBhavBar(
                trade_date=row.trade_date,
                symbol=row.symbol,
                series=row.series,
                isin=row.isin,
                instrument_name=row.instrument_name,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                prev_close=row.prev_close,
                volume=row.volume,
                turnover=row.turnover,
                source_key=row.source_key,
                run_id=run_id,
            )
        )
    session.flush()


def list_session_dates(session: Session, *, as_of: date, limit: int = 20) -> list[date]:
    rows = session.scalars(
        select(NseBhavBar.trade_date)
        .where(NseBhavBar.trade_date <= as_of)
        .distinct()
        .order_by(NseBhavBar.trade_date.desc())
        .limit(limit)
    ).all()
    return sorted(rows)


def count_bars(session: Session, trade_date: date, *, series: str | None = None) -> int:
    stmt = select(func.count()).select_from(NseBhavBar).where(NseBhavBar.trade_date == trade_date)
    if series is not None:
        stmt = stmt.where(NseBhavBar.series == series)
    return int(session.scalar(stmt) or 0)


def load_bars_for_dates(
    session: Session,
    dates: list[date],
    *,
    series: str | None = "EQ",
) -> list[NseBhavBar]:
    if not dates:
        return []
    stmt = select(NseBhavBar).where(NseBhavBar.trade_date.in_(dates))
    if series is not None:
        stmt = stmt.where(NseBhavBar.series == series)
    return list(session.scalars(stmt).all())


def load_day_bars(
    session: Session,
    trade_date: date,
    *,
    series: str | None = None,
) -> list[NseBhavBar]:
    stmt = select(NseBhavBar).where(NseBhavBar.trade_date == trade_date)
    if series is not None:
        stmt = stmt.where(NseBhavBar.series == series)
    return list(session.scalars(stmt.order_by(NseBhavBar.symbol)).all())


def prior_session_date(session: Session, as_of: date) -> date | None:
    return session.scalar(
        select(NseBhavBar.trade_date)
        .where(NseBhavBar.trade_date < as_of)
        .distinct()
        .order_by(NseBhavBar.trade_date.desc())
        .limit(1)
    )


def bars_by_symbol(bars: list[NseBhavBar]) -> dict[str, NseBhavBar]:
    return {bar.symbol: bar for bar in bars}


def _synthetic_bar(row: ParsedBhavRow) -> NseBhavBar:
    """In-memory bar for pre-write reconcile (not added to the session)."""
    return NseBhavBar(
        trade_date=row.trade_date,
        symbol=row.symbol,
        series=row.series,
        isin=row.isin,
        instrument_name=row.instrument_name,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        prev_close=row.prev_close,
        volume=row.volume,
        turnover=row.turnover,
        source_key=row.source_key,
    )


def commit_bhav_run(session: Session, run_id: int) -> BhavImportRun:
    """Validate, reconcile against projected day, then replace-day upsert."""
    run = session.get(BhavImportRun, run_id)
    if run is None:
        raise LookupError(f"Unknown bhav run {run_id}")
    if run.status not in {"staged", "validated"}:
        raise ValueError(f"Run {run_id} cannot commit from status={run.status}")

    rows = parse_bhav_file(Path(run.staged_path))
    validation = validate_parsed_rows(rows)
    run.validation_report = validation.as_dict()
    run.trade_date = validation.trade_date
    run.row_count_all = validation.row_count_all
    run.row_count_eq = validation.row_count_eq
    if not validation.ok or validation.trade_date is None:
        run.status = "failed"
        run.error_message = "; ".join(validation.errors[:5]) or "validation failed"
        session.flush()
        return run

    trade_date = validation.trade_date
    new_bars = [_synthetic_bar(row) for row in rows]
    new_eq = [b for b in new_bars if b.series == "EQ"]

    # Project Last20 as if this day were stored (exclude old copy of same date).
    prior_dates = [
        d for d in list_session_dates(session, as_of=trade_date, limit=20) if d != trade_date
    ]
    session_dates = sorted(prior_dates + [trade_date])[-20:]
    older = load_bars_for_dates(
        session, [d for d in session_dates if d != trade_date], series="EQ"
    )
    window_bars = [*older, *new_eq]
    ranks = volume_ranks(window_bars, series="EQ")

    portfolio = list(session.scalars(select(PivotPortfolioSymbol)).all())
    portfolio_a = [p.symbol for p in portfolio if p.portfolio_a]
    pivot_symbols = [p.symbol for p in portfolio] or sorted({b.symbol for b in new_eq})[:50]
    prior_date = max((d for d in session_dates if d < trade_date), default=None)
    prior_map = (
        bars_by_symbol(load_day_bars(session, prior_date, series="EQ")) if prior_date else {}
    )
    last_map = bars_by_symbol(new_eq)
    pivots = floor_pivots_for_symbols(
        as_of=trade_date,
        symbols=pivot_symbols,
        prior_bars=prior_map,
        last_bars=last_map,
    )

    reconcile = reconcile_day(
        expected_all=validation.row_count_all,
        expected_eq=validation.row_count_eq,
        stored_all=len(new_bars),
        stored_eq=len(new_eq),
        session_dates=session_dates,
        as_of=trade_date,
        ranks=ranks,
        pivots=pivots,
        portfolio_a_symbols=portfolio_a,
    )
    run.reconcile_report = reconcile.as_dict()
    if not reconcile.ok:
        run.status = "failed"
        run.error_message = "; ".join(reconcile.errors[:5]) or "reconcile failed"
        session.flush()
        return run

    _replace_day_bars(session, trade_date, rows, run.run_id)
    prune_bhav_sessions(session, MAX_BHAV_SESSIONS)
    # Excel Daily Vol Exp = AllSymbols AvgQty20Days+x%, not Last20×1.1. Keep seeded
    # AllSymbols until we intentionally rebuild; otherwise fill from bars.
    if not _has_all_symbols_vol_exp(session):
        rebuild_vol_exp_from_bars(session, before=trade_date)
    run.status = "committed"
    run.committed_at = datetime.now(timezone.utc)
    run.error_message = None
    session.flush()
    return run


def available_trade_dates(session: Session) -> list[date]:
    return list(
        session.scalars(
            select(NseBhavBar.trade_date).distinct().order_by(NseBhavBar.trade_date.desc())
        ).all()
    )


def latest_bhav_trade_date(session: Session) -> date | None:
    dates = available_trade_dates(session)
    return dates[0] if dates else None


def lookup_bhav_close(
    session: Session,
    symbol: str,
    as_of: date,
    *,
    series_order: tuple[str, ...] = ("EQ", "BE"),
) -> tuple[Decimal, str] | None:
    """Exact-date NSE bhav close for a ticker (EQ preferred, then BE)."""
    key = symbol.strip().upper()
    if not key:
        return None
    for series in series_order:
        bar = session.scalar(
            select(NseBhavBar).where(
                NseBhavBar.trade_date == as_of,
                NseBhavBar.symbol == key,
                NseBhavBar.series == series,
            )
        )
        if bar is not None:
            return Decimal(bar.close), series
    return None


def prune_bhav_sessions(session: Session, keep: int = MAX_BHAV_SESSIONS) -> int:
    """Delete bars for sessions older than the newest ``keep`` trade dates."""
    dates = available_trade_dates(session)
    drop = dates[keep:]
    if not drop:
        return 0
    result = session.execute(delete(NseBhavBar).where(NseBhavBar.trade_date.in_(drop)))
    session.flush()
    return int(result.rowcount or 0)


def replace_vol_exp_stats(
    session: Session,
    rows: list[tuple[str, Decimal, int | None]],
    *,
    source: str,
) -> int:
    session.execute(delete(PivotVolExp))
    for symbol, vol_exp, rank in rows:
        session.add(
            PivotVolExp(symbol=symbol, vol_exp=vol_exp, rank=rank, source=source)
        )
    session.flush()
    return len(rows)


def rebuild_vol_exp_from_bars(session: Session, *, before: date) -> int:
    """Vol Exp = avg EQ volume over sessions before ``before`` (≤20) × 1.1."""
    dates = [d for d in available_trade_dates(session) if d < before][:MAX_BHAV_SESSIONS]
    ranks = volume_ranks(load_bars_for_dates(session, dates, series="EQ"), series="EQ")
    return replace_vol_exp_stats(
        session,
        [(r.symbol, r.avg_volume_plus_10pct, r.rank) for r in ranks],
        source="bars",
    )


def _has_all_symbols_vol_exp(session: Session) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(PivotVolExp)
            .where(PivotVolExp.source == "all_symbols")
        )
        or 0
    ) > 0


def load_vol_exp_map(session: Session) -> dict[str, Decimal]:
    return {
        row.symbol: row.vol_exp
        for row in session.scalars(select(PivotVolExp)).all()
    }


def upsert_portfolio_symbols(
    session: Session,
    rows: list[dict[str, Any]],
) -> int:
    """Replace-or-update portfolio symbols from seed/API payloads.

    Duplicate symbols in the payload keep the last row. Re-runs are idempotent.
    """
    by_symbol: dict[str, dict[str, Any]] = {}
    for raw in rows:
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        by_symbol[symbol] = {**raw, "symbol": symbol}

    count = 0
    for symbol, raw in by_symbol.items():
        existing = session.get(PivotPortfolioSymbol, symbol)
        if existing is None:
            existing = PivotPortfolioSymbol(symbol=symbol)
            session.add(existing)
        existing.dummy = bool(raw.get("dummy", False))
        existing.portfolio_a = bool(raw.get("portfolio_a", False))
        existing.uptrend = bool(raw.get("uptrend", False))
        existing.support_note = raw.get("support_note")
        existing.buy_note = raw.get("buy_note")
        existing.sma_50 = raw.get("sma_50")
        existing.sma_100 = raw.get("sma_100")
        existing.sma_200 = raw.get("sma_200")
        existing.notes = raw.get("notes")
        count += 1
    session.flush()
    return count


def delete_portfolio_symbol(session: Session, symbol: str) -> bool:
    """Remove one selected-firm symbol. Returns False if it was not present."""
    key = symbol.strip().upper()
    existing = session.get(PivotPortfolioSymbol, key)
    if existing is None:
        return False
    session.delete(existing)
    session.flush()
    return True


def known_bhav_symbols(session: Session, *, series: tuple[str, ...] = ("EQ", "BE")) -> set[str]:
    """NSE tickers that appear in stored bhav (EQ/BE by default)."""
    return set(
        session.scalars(
            select(NseBhavBar.symbol)
            .where(NseBhavBar.series.in_(series))
            .distinct()
        ).all()
    )


def search_bhav_symbols(
    session: Session,
    query: str,
    *,
    limit: int = 20,
    series: tuple[str, ...] = ("EQ", "BE"),
) -> list[str]:
    """Prefix search over known EQ/BE tickers (min 2 chars)."""
    q = query.strip().upper()
    if len(q) < 2:
        return []
    return list(
        session.scalars(
            select(NseBhavBar.symbol)
            .where(NseBhavBar.series.in_(series))
            .where(NseBhavBar.symbol.like(f"{q}%"))
            .distinct()
            .order_by(NseBhavBar.symbol)
            .limit(limit)
        ).all()
    )


def sync_bhav_file(session: Session, path: Path) -> BhavImportRun:
    """CLI helper: stage a local file then commit through the verification loop."""
    content = Path(path).read_bytes()
    run = stage_bhav_upload(session, filename=Path(path).name, content=content)
    # Keep a stable copy under uploads even if source moves.
    staged = Path(run.staged_path)
    if Path(path).resolve() != staged.resolve():
        shutil.copy2(path, staged)
    return commit_bhav_run(session, run.run_id)
