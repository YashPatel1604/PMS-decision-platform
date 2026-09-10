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

# Keep newest 21 sessions on disk/DB (Last20 window + one prior day).
MAX_BHAV_SESSIONS = 21
# Excel Last20Days_test / AvgQty20Days+x% window length.
LAST20_SESSIONS = 20


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
    """Newest ``limit`` trade dates on/before as_of (may include large gaps)."""
    rows = session.scalars(
        select(NseBhavBar.trade_date)
        .where(NseBhavBar.trade_date <= as_of)
        .distinct()
        .order_by(NseBhavBar.trade_date.desc())
        .limit(limit)
    ).all()
    return sorted(rows)


def last_working_sessions(
    session: Session,
    *,
    as_of: date,
    limit: int = LAST20_SESSIONS,
    max_gap_days: int = 10,
) -> list[date]:
    """Last ≤20 NSE working days ending at as_of (contiguous; stop on a long gap).

    Matches Excel Last20Days_test: add today, drop the 21st prior session — never
    stitch across year-long holes (e.g. 2024 seed + 2026 daily).
    """
    newest_first = session.scalars(
        select(NseBhavBar.trade_date)
        .where(NseBhavBar.trade_date <= as_of)
        .distinct()
        .order_by(NseBhavBar.trade_date.desc())
        .limit(max(limit * 3, MAX_BHAV_SESSIONS))
    ).all()
    if not newest_first:
        return []
    out: list[date] = [newest_first[0]]
    for day in newest_first[1:]:
        if (out[-1] - day).days > max_gap_days:
            break
        out.append(day)
        if len(out) >= limit:
            break
    return sorted(out)


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


def prior_session_date(
    session: Session, as_of: date, *, max_gap_days: int = 10
) -> date | None:
    """Nearest earlier bhav day, or None if the gap is too large (sparse history)."""
    prior = session.scalar(
        select(NseBhavBar.trade_date)
        .where(NseBhavBar.trade_date < as_of)
        .distinct()
        .order_by(NseBhavBar.trade_date.desc())
        .limit(1)
    )
    if prior is None:
        return None
    # ponytail: no full holiday calendar; 10d covers long weekends, not year-long seed gaps
    if (as_of - prior).days > max_gap_days:
        return None
    return prior


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
    # Snapshot Vol Exp while Last20 still includes today; then drop the 21st day.
    snapshot_vol_exp_for_as_of(session, trade_date)
    prune_bhav_sessions(session, MAX_BHAV_SESSIONS)
    run.status = "committed"
    run.committed_at = datetime.now(timezone.utc)
    run.error_message = None
    session.flush()
    from pms_platform.market_data.daily_edit_bhav import maybe_apply_committed_bhav

    maybe_apply_committed_bhav(run.staged_path)
    return run


def available_trade_dates(session: Session) -> list[date]:
    return list(
        session.scalars(
            select(NseBhavBar.trade_date).distinct().order_by(NseBhavBar.trade_date.desc())
        ).all()
    )


def has_bhav_trade_date(session: Session, trade_date: date) -> bool:
    """True when any committed bhav bars exist for that session day."""
    return (
        session.scalar(
            select(NseBhavBar.trade_date).where(NseBhavBar.trade_date == trade_date).limit(1)
        )
        is not None
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
    session.execute(delete(PivotVolExp).where(PivotVolExp.as_of_date.in_(drop)))
    session.flush()
    return int(result.rowcount or 0)


def snapshot_vol_exp_for_as_of(session: Session, as_of: date) -> int:
    """Daily Vol Exp = Last20 avg vol ×1.1 (top 50 by turnover) or ×1.2 (rest).

    Prefer EQ bars; include BE-only names (e.g. E2E) so portfolio Vol Exp is not blank.
    Call after writing that day's bars and before pruning older sessions so the
    window still matches Excel Last20Days_test (add today, drop the 21st day later).
    """
    dates = last_working_sessions(session, as_of=as_of, limit=LAST20_SESSIONS)
    if not dates:
        return 0
    eq_bars = load_bars_for_dates(session, dates, series="EQ")
    be_bars = load_bars_for_dates(session, dates, series="BE")
    eq_syms = {b.symbol for b in eq_bars}
    # BE-only listings still need Vol Exp (Excel Daily includes SctySrs=BE).
    merged = list(eq_bars) + [b for b in be_bars if b.symbol not in eq_syms]
    ranks = volume_ranks(merged, series=None)
    session.execute(delete(PivotVolExp).where(PivotVolExp.as_of_date == as_of))
    for row in ranks:
        session.add(
            PivotVolExp(
                as_of_date=as_of,
                symbol=row.symbol,
                vol_exp=row.avg_volume_plus_10pct,
                rank=row.rank,
                source="last20",
            )
        )
    session.flush()
    return len(ranks)


def replace_vol_exp_stats(
    session: Session,
    rows: list[tuple[str, Decimal, int | None]],
    *,
    source: str,
    as_of: date,
) -> int:
    session.execute(delete(PivotVolExp).where(PivotVolExp.as_of_date == as_of))
    for symbol, vol_exp, rank in rows:
        session.add(
            PivotVolExp(
                as_of_date=as_of,
                symbol=symbol,
                vol_exp=vol_exp,
                rank=rank,
                source=source,
            )
        )
    session.flush()
    return len(rows)


def rebuild_vol_exp_from_bars(session: Session, *, before: date) -> int:
    """Legacy helper: Vol Exp from sessions strictly before ``before``."""
    dates = [d for d in available_trade_dates(session) if d < before][:MAX_BHAV_SESSIONS]
    eq_bars = load_bars_for_dates(session, dates, series="EQ")
    be_bars = load_bars_for_dates(session, dates, series="BE")
    eq_syms = {b.symbol for b in eq_bars}
    merged = list(eq_bars) + [b for b in be_bars if b.symbol not in eq_syms]
    ranks = volume_ranks(merged, series=None)
    return replace_vol_exp_stats(
        session,
        [(r.symbol, r.avg_volume_plus_10pct, r.rank) for r in ranks],
        source="bars",
        as_of=before,
    )


def load_vol_exp_map(session: Session, as_of: date) -> dict[str, Decimal]:
    """Vol Exp snapshot for ``as_of``; build from Last20 bars if missing."""
    rows = list(
        session.scalars(select(PivotVolExp).where(PivotVolExp.as_of_date == as_of)).all()
    )
    if not rows and has_bhav_trade_date(session, as_of):
        snapshot_vol_exp_for_as_of(session, as_of)
        rows = list(
            session.scalars(select(PivotVolExp).where(PivotVolExp.as_of_date == as_of)).all()
        )
    return {row.symbol: row.vol_exp for row in rows}


def backfill_vol_exp_snapshots(session: Session) -> int:
    """Snapshot Vol Exp for every kept bhav day (oldest → newest).

    Leaves existing ``all_symbols`` snapshots alone (Excel Daily numbers).
    """
    total = 0
    for day in sorted(available_trade_dates(session)):
        existing = session.scalar(
            select(PivotVolExp.source).where(PivotVolExp.as_of_date == day).limit(1)
        )
        if existing == "all_symbols":
            continue
        total += snapshot_vol_exp_for_as_of(session, day)
    return total


def upsert_portfolio_symbols(
    session: Session,
    rows: list[dict[str, Any]],
) -> int:
    """Replace-or-update portfolio symbols from seed/API payloads.

    Duplicate symbols in the payload keep the last row. Re-runs are idempotent.
    New symbols append at the end (``sort_order`` = max+1) so selection order is kept.
    """
    by_symbol: dict[str, dict[str, Any]] = {}
    for raw in rows:
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        by_symbol[symbol] = {**raw, "symbol": symbol}

    next_order = int(
        session.scalar(
            select(func.coalesce(func.max(PivotPortfolioSymbol.sort_order), 0))
        )
        or 0
    )

    count = 0
    for symbol, raw in by_symbol.items():
        existing = session.get(PivotPortfolioSymbol, symbol)
        if existing is None:
            next_order += 1
            existing = PivotPortfolioSymbol(
                symbol=symbol,
                sort_order=int(raw["sort_order"])
                if raw.get("sort_order") is not None
                else next_order,
            )
            session.add(existing)
            next_order = max(next_order, existing.sort_order)
        elif raw.get("sort_order") is not None:
            existing.sort_order = int(raw["sort_order"])
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
