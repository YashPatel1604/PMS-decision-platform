"""Unified watchlist refresh: resolve + fundamentals + alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.fundamentals.providers.nse import NseTarget
from pms_platform.fundamentals.service import FundamentalsSyncResult, sync_fundamentals
from pms_platform.models.watchlist_refresh_lock import WatchlistRefreshLock
from pms_platform.watchlists import alerts as wa
from pms_platform.watchlists import service as wl

LOCK_TTL = timedelta(minutes=15)


class WatchlistRefreshInProgressError(wl.WatchlistError):
    """Another refresh is already running for this watchlist."""


@dataclass(frozen=True)
class ResolutionRefreshStats:
    resolved: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class FundamentalsRefreshStats:
    csv_inserted: int
    csv_updated: int
    csv_skipped: int
    csv_invalid: int
    snapshots_written: int
    identifiers_processed: int


@dataclass(frozen=True)
class AlertsRefreshStats:
    inserted: int
    skipped: int
    matched: int


@dataclass(frozen=True)
class WatchlistRefreshResult:
    watchlist_id: int
    watchlist_name: str
    resolution: ResolutionRefreshStats
    fundamentals: FundamentalsRefreshStats | None
    alerts: AlertsRefreshStats
    duration_ms: int


@dataclass(frozen=True)
class SyncWatchlistsResult:
    watchlists_refreshed: int
    fundamentals: FundamentalsRefreshStats | None
    results: tuple[WatchlistRefreshResult, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clear_expired_locks(session: Session) -> None:
    now = _utcnow()
    session.execute(delete(WatchlistRefreshLock).where(WatchlistRefreshLock.expires_at <= now))


def acquire_refresh_lock(session: Session, watchlist_id: int) -> None:
    """Acquire a refresh lock or raise if another refresh is in progress."""
    wl.get_watchlist(session, watchlist_id)
    _clear_expired_locks(session)
    existing = session.get(WatchlistRefreshLock, watchlist_id)
    if existing is not None:
        raise WatchlistRefreshInProgressError(
            f"Refresh already in progress for watchlist {watchlist_id}"
        )
    now = _utcnow()
    session.add(
        WatchlistRefreshLock(
            watchlist_id=watchlist_id,
            locked_at=now,
            expires_at=now + LOCK_TTL,
        )
    )
    session.flush()


def release_refresh_lock(session: Session, watchlist_id: int) -> None:
    session.execute(
        delete(WatchlistRefreshLock).where(WatchlistRefreshLock.watchlist_id == watchlist_id)
    )
    session.flush()


def _fundamentals_stats(result: FundamentalsSyncResult) -> FundamentalsRefreshStats:
    imp = result.import_result
    return FundamentalsRefreshStats(
        csv_inserted=imp.inserted if imp else 0,
        csv_updated=imp.updated if imp else 0,
        csv_skipped=imp.skipped if imp else 0,
        csv_invalid=imp.invalid if imp else 0,
        snapshots_written=result.snapshots_written,
        identifiers_processed=result.identifiers_processed,
    )


def _watchlist_bse_codes(session: Session, watchlist_id: int) -> list[str]:
    """Distinct BSE codes for members of one watchlist."""
    from pms_platform.models.watchlist import WatchlistMember
    from pms_platform.market_data.bse_scrip_universe import resolve_bse_code

    members = session.scalars(
        select(WatchlistMember).where(WatchlistMember.watchlist_id == watchlist_id)
    ).all()
    codes: list[str] = []
    seen: set[str] = set()
    for member in members:
        candidates = [
            member.bse_code,
            resolve_bse_code(
                nse_symbol=member.nse_symbol,
                company_name=member.display_name,
                isin=member.isin,
            ),
        ]
        for raw in candidates:
            code = str(raw or "").strip()
            if code.endswith(".0"):
                code = code[:-2]
            # BSE scrip codes are numeric; skip NSE symbols parked in bse_code.
            if not code or not code.isdigit() or code in seen:
                continue
            seen.add(code)
            codes.append(code)
    return codes


def refresh_watchlist(
    session: Session,
    watchlist_id: int,
    *,
    external_dir: Path | None = None,
    include_fundamentals: bool = False,
    fundamentals_result: FundamentalsSyncResult | None = None,
) -> WatchlistRefreshResult:
    """Resolve symbols, optionally refresh fundamentals, and poll alerts."""
    started = _utcnow()
    watchlist = wl.get_watchlist(session, watchlist_id)
    acquire_refresh_lock(session, watchlist_id)
    try:
        resolution_raw = wl.resolve_stale_members(session, watchlist_id)
        resolution = ResolutionRefreshStats(
            resolved=resolution_raw["resolved"],
            failed=resolution_raw["failed"],
            skipped=resolution_raw["skipped"],
        )

        fundamentals_stats: FundamentalsRefreshStats | None = None
        if include_fundamentals:
            codes = _watchlist_bse_codes(session, watchlist_id)
            # Prefer filling gaps first; only re-pull everything when already complete.
            to_fetch = codes_missing_valuation(session, codes) or codes
            fund = fundamentals_result or sync_fundamentals(
                session,
                external_dir=external_dir or settings.external_data_dir,
                bse_codes=to_fetch or None,
            )
            fundamentals_stats = _fundamentals_stats(fund)
            # Screener prefers materialized metrics; keep them in sync with snapshots.
            from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics

            rebuild_watchlist_metrics(session, watchlist_id)

        alert_raw = wa.poll_watchlist_alerts(session, watchlist_id)
        alerts = AlertsRefreshStats(
            inserted=alert_raw.inserted,
            skipped=alert_raw.skipped,
            matched=alert_raw.matched,
        )

        elapsed_ms = int((_utcnow() - started).total_seconds() * 1000)
        return WatchlistRefreshResult(
            watchlist_id=watchlist_id,
            watchlist_name=watchlist.name,
            resolution=resolution,
            fundamentals=fundamentals_stats,
            alerts=alerts,
            duration_ms=elapsed_ms,
        )
    finally:
        release_refresh_lock(session, watchlist_id)


def _watchlist_nse_targets(session: Session, watchlist_id: int) -> list[NseTarget]:
    """NSE symbols with BSE codes for one watchlist (current + historical aliases)."""
    from pms_platform.models.watchlist import WatchlistMember
    from pms_platform.watchlists.identity_aliases import all_identifiers_for_security

    members = session.scalars(
        select(WatchlistMember).where(WatchlistMember.watchlist_id == watchlist_id)
    ).all()
    out: list[NseTarget] = []
    seen: set[str] = set()
    for member in members:
        nse = str(member.nse_symbol or "").strip().upper()
        bse = str(member.bse_code or "").strip()
        if bse.endswith(".0"):
            bse = bse[:-2]
        pairs = [(nse, bse)] if nse and bse.isdigit() else []
        if member.security_id:
            id_map = {t: v for t, v in all_identifiers_for_security(session, member.security_id)}
            hist_nse = id_map.get("NSE_SYMBOL")
            hist_bse = id_map.get("BSE_CODE") or bse
            if hist_nse and hist_bse.isdigit():
                pairs.append((hist_nse.upper(), hist_bse))
        for sym, code in pairs:
            if not sym or not code.isdigit() or sym in seen:
                continue
            seen.add(sym)
            out.append(NseTarget(nse_symbol=sym, bse_code=code, security_id=member.security_id))
    return out


def _all_watchlist_nse_targets(session: Session) -> list[NseTarget]:
    out: list[NseTarget] = []
    seen: set[str] = set()
    for row in wl.list_watchlists(session):
        for target in _watchlist_nse_targets(session, row.watchlist_id):
            if target.nse_symbol not in seen:
                seen.add(target.nse_symbol)
                out.append(target)
    return out


def _all_watchlist_bse_codes(session: Session) -> list[str]:
    """Distinct BSE codes across every watchlist."""
    codes: list[str] = []
    seen: set[str] = set()
    for row in wl.list_watchlists(session):
        for code in _watchlist_bse_codes(session, row.watchlist_id):
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def refresh_watchlist_fundamentals(
    session: Session,
    *,
    external_dir: Path | None = None,
    watchlist_id: int | None = None,
) -> FundamentalsSyncResult:
    """Fetch BSE fundamentals for watchlist codes, write DB, recompute snapshots.

    No symbol resolution or alert polling — intended for scheduled jobs and
    manual fundamentals-only refresh. Screener reads the persisted snapshots.
    """
    from pms_platform.watchlists.metrics_cache import (
        rebuild_all_watchlist_metrics,
        rebuild_watchlist_metrics,
    )

    if watchlist_id is not None:
        codes = _watchlist_bse_codes(session, watchlist_id)
        nse_targets = _watchlist_nse_targets(session, watchlist_id)
    else:
        codes = _all_watchlist_bse_codes(session)
        nse_targets = _all_watchlist_nse_targets(session)
    result = sync_fundamentals(
        session,
        external_dir=external_dir or settings.external_data_dir,
        bse_codes=codes or None,
        nse_targets=nse_targets or None,
    )
    if watchlist_id is not None:
        rebuild_watchlist_metrics(session, watchlist_id)
    else:
        rebuild_all_watchlist_metrics(session)
    session.flush()
    return result


def sync_all_watchlists(
    session: Session,
    *,
    external_dir: Path | None = None,
    include_fundamentals: bool = True,
    watchlist_id: int | None = None,
) -> SyncWatchlistsResult:
    """Resolve + poll alerts first, then fundamentals + metrics (codes after resolve)."""
    if watchlist_id is not None:
        watchlists = [wl.get_watchlist(session, watchlist_id)]
    else:
        watchlists = wl.list_watchlists(session)

    # Resolve symbols before fundamentals so newly filled BSE codes are included.
    results: list[WatchlistRefreshResult] = []
    for row in watchlists:
        results.append(
            refresh_watchlist(
                session,
                row.watchlist_id,
                external_dir=external_dir,
                include_fundamentals=False,
            )
        )

    fundamentals_stats: FundamentalsRefreshStats | None = None
    if include_fundamentals:
        if watchlist_id is not None:
            scoped_codes = _watchlist_bse_codes(session, watchlist_id)
            nse_targets = _watchlist_nse_targets(session, watchlist_id)
        else:
            scoped_codes = _all_watchlist_bse_codes(session) or None
            nse_targets = _all_watchlist_nse_targets(session)
        fundamentals_result = sync_fundamentals(
            session,
            external_dir=external_dir or settings.external_data_dir,
            bse_codes=scoped_codes,
            nse_targets=nse_targets or None,
        )
        fundamentals_stats = _fundamentals_stats(fundamentals_result)
        from pms_platform.watchlists.metrics_cache import rebuild_all_watchlist_metrics

        rebuild_all_watchlist_metrics(session)

    return SyncWatchlistsResult(
        watchlists_refreshed=len(results),
        fundamentals=fundamentals_stats,
        results=tuple(results),
    )


@dataclass(frozen=True)
class WatchlistQuotesRefreshResult:
    bse_codes: int
    valuation_updated: int
    promoter_updated: int
    metrics_rows: int


def refresh_watchlist_quotes(
    session: Session,
    *,
    watchlist_id: int | None = None,
    bse_codes: list[str] | None = None,
) -> WatchlistQuotesRefreshResult:
    """Fetch valuation + promoter + price returns; rebuild materialized screener cache."""
    from pms_platform.fundamentals.providers.promoter import refresh_promoter_snapshots
    from pms_platform.fundamentals.providers.valuation import refresh_valuation_snapshots
    from pms_platform.fundamentals.service import _valuation_enrichment
    from pms_platform.market_data.price_returns import refresh_price_returns
    from pms_platform.watchlists.metrics_cache import (
        rebuild_all_watchlist_metrics,
        rebuild_watchlist_metrics,
    )

    if bse_codes is not None:
        codes = list(dict.fromkeys(str(c).strip() for c in bse_codes if c and str(c).strip()))
    elif watchlist_id is not None:
        codes = _watchlist_bse_codes(session, watchlist_id)
    else:
        codes = _all_watchlist_bse_codes(session)

    val_updated = 0
    prom_updated = 0
    if codes:
        trailing_sales, pat_cagr = _valuation_enrichment(session, codes)
        val = refresh_valuation_snapshots(
            session,
            codes,
            force=False,
            trailing_sales_by_code=trailing_sales,
            pat_3y_cagr_by_code=pat_cagr,
        )
        val_updated = val.inserted + val.updated
        prom = refresh_promoter_snapshots(session, codes)
        prom_updated = prom.inserted + prom.updated
        refresh_price_returns(session, [("BSE_CODE", code) for code in codes])

    if watchlist_id is not None:
        metrics_rows = rebuild_watchlist_metrics(session, watchlist_id)
    else:
        metrics_rows = rebuild_all_watchlist_metrics(session)

    session.flush()
    return WatchlistQuotesRefreshResult(
        bse_codes=len(codes),
        valuation_updated=val_updated,
        promoter_updated=prom_updated,
        metrics_rows=metrics_rows,
    )


def codes_missing_valuation(session: Session, bse_codes: list[str]) -> list[str]:
    """BSE codes with no valuation_snapshots row yet."""
    from pms_platform.models.valuation_snapshot import ValuationSnapshot

    codes = list(dict.fromkeys(str(c).strip() for c in bse_codes if c and str(c).strip()))
    if not codes:
        return []
    have = set(
        session.scalars(
            select(ValuationSnapshot.identifier).where(
                ValuationSnapshot.identifier_type == "BSE_CODE",
                ValuationSnapshot.identifier.in_(codes),
            )
        ).all()
    )
    return [c for c in codes if c not in have]


def enrich_watchlist_for_codes(
    session: Session,
    watchlist_id: int,
    bse_codes: list[str],
) -> None:
    """Populate screener data for BSE codes after add (fundamentals + quotes + metrics).

    Best-effort: member stays saved if a provider call fails.
    # ponytail: syncs one/few codes on add; full-list schedule still owns nightly refresh.
    """
    codes = list(dict.fromkeys(str(c).strip() for c in bse_codes if c and str(c).strip()))
    if not codes:
        from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics

        rebuild_watchlist_metrics(session, watchlist_id)
        session.flush()
        return
    try:
        sync_fundamentals(
            session,
            external_dir=settings.external_data_dir,
            bse_codes=codes,
        )
    except Exception:
        # Fall back to quotes-only so PE/mcap/returns still appear.
        refresh_watchlist_quotes(session, watchlist_id=watchlist_id, bse_codes=codes)
        return
    from pms_platform.watchlists.metrics_cache import rebuild_watchlist_metrics

    rebuild_watchlist_metrics(session, watchlist_id)
    session.flush()
