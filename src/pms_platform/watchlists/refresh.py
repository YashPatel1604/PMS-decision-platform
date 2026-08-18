"""Unified watchlist refresh: resolve + fundamentals + alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.config import settings
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
            if not code or code in seen:
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
            fund = fundamentals_result or sync_fundamentals(
                session,
                external_dir=external_dir or settings.external_data_dir,
                bse_codes=_watchlist_bse_codes(session, watchlist_id),
            )
            fundamentals_stats = _fundamentals_stats(fund)

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
    else:
        codes = _all_watchlist_bse_codes(session)
    result = sync_fundamentals(
        session,
        external_dir=external_dir or settings.external_data_dir,
        bse_codes=codes or None,
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
    """Refresh fundamentals once, then resolve + poll alerts for each watchlist."""
    fundamentals_result: FundamentalsSyncResult | None = None
    fundamentals_stats: FundamentalsRefreshStats | None = None
    if include_fundamentals:
        if watchlist_id is not None:
            scoped_codes = _watchlist_bse_codes(session, watchlist_id)
        else:
            scoped_codes = _all_watchlist_bse_codes(session) or None
        fundamentals_result = sync_fundamentals(
            session,
            external_dir=external_dir or settings.external_data_dir,
            bse_codes=scoped_codes,
        )
        fundamentals_stats = _fundamentals_stats(fundamentals_result)
        from pms_platform.watchlists.metrics_cache import rebuild_all_watchlist_metrics

        rebuild_all_watchlist_metrics(session)

    if watchlist_id is not None:
        watchlists = [wl.get_watchlist(session, watchlist_id)]
    else:
        watchlists = wl.list_watchlists(session)

    results: list[WatchlistRefreshResult] = []
    for row in watchlists:
        results.append(
            refresh_watchlist(
                session,
                row.watchlist_id,
                external_dir=external_dir,
                include_fundamentals=False,
                fundamentals_result=fundamentals_result,
            )
        )

    return SyncWatchlistsResult(
        watchlists_refreshed=len(results),
        fundamentals=fundamentals_stats,
        results=tuple(results),
    )
