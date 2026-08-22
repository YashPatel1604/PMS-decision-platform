"""Watchlist data-quality health reports."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import validated_fundamentals_provider
from pms_platform.models.watchlist import WatchlistAlert
from pms_platform.models.watchlist_refresh_lock import WatchlistRefreshLock
from pms_platform.watchlists import alerts as wa
from pms_platform.watchlists import resolution as res
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl


@dataclass(frozen=True)
class WatchlistHealthRow:
    watchlist_id: int
    name: str
    member_count: int
    resolved_count: int
    unresolved_count: int
    stale_resolution_count: int
    with_fundamentals_count: int
    missing_fundamentals_count: int
    stale_fundamentals_count: int
    unacknowledged_alerts: int
    refresh_locked: bool


@dataclass(frozen=True)
class WatchlistsHealthReport:
    fundamentals_provider: str
    watchlist_count: int
    total_members: int
    total_unresolved: int
    total_stale_resolution: int
    total_missing_fundamentals: int
    total_stale_fundamentals: int
    total_unacknowledged_alerts: int
    any_refresh_locked: bool
    watchlists: tuple[WatchlistHealthRow, ...]


def build_watchlist_health(session: Session, watchlist_id: int) -> WatchlistHealthRow:
    watchlist = wl.get_watchlist(session, watchlist_id)
    members = wl.list_members(session, watchlist_id)
    resolved = unresolved = stale_res = 0
    with_fund = missing_fund = stale_fund = 0

    from pms_platform.models.watchlist_member_metrics import WatchlistMemberMetrics
    from pms_platform.fundamentals.catalog import WATCHLIST_METRICS_VERSION

    cached = {
        row.member_id: row
        for row in session.scalars(
            select(WatchlistMemberMetrics).where(
                WatchlistMemberMetrics.watchlist_id == watchlist_id,
                WatchlistMemberMetrics.computation_version == WATCHLIST_METRICS_VERSION,
            )
        ).all()
    }

    for member in members:
        if member.resolution_status == "RESOLVED" and not res.is_resolution_stale(member):
            resolved += 1
        else:
            unresolved += 1
        if res.is_resolution_stale(member):
            stale_res += 1
        hit = cached.get(member.member_id)
        if hit is not None:
            has_fund, is_stale = hit.has_fundamentals, hit.fundamentals_stale
        else:
            has_fund, is_stale = scr.member_fundamentals_status(session, member)
        if has_fund:
            with_fund += 1
            if is_stale:
                stale_fund += 1
        else:
            missing_fund += 1

    unack = (
        session.scalar(
            select(func.count())
            .select_from(WatchlistAlert)
            .where(
                WatchlistAlert.watchlist_id == watchlist_id,
                WatchlistAlert.acknowledged.is_(False),
            )
        )
        or 0
    )
    locked = session.get(WatchlistRefreshLock, watchlist_id) is not None

    return WatchlistHealthRow(
        watchlist_id=watchlist_id,
        name=watchlist.name,
        member_count=len(members),
        resolved_count=resolved,
        unresolved_count=unresolved,
        stale_resolution_count=stale_res,
        with_fundamentals_count=with_fund,
        missing_fundamentals_count=missing_fund,
        stale_fundamentals_count=stale_fund,
        unacknowledged_alerts=unack,
        refresh_locked=locked,
    )


def build_all_watchlists_health(session: Session) -> WatchlistsHealthReport:
    watchlists = wl.list_watchlists(session)
    rows = tuple(build_watchlist_health(session, row.watchlist_id) for row in watchlists)

    return WatchlistsHealthReport(
        fundamentals_provider=validated_fundamentals_provider(),
        watchlist_count=len(rows),
        total_members=sum(row.member_count for row in rows),
        total_unresolved=sum(row.unresolved_count for row in rows),
        total_stale_resolution=sum(row.stale_resolution_count for row in rows),
        total_missing_fundamentals=sum(row.missing_fundamentals_count for row in rows),
        total_stale_fundamentals=sum(row.stale_fundamentals_count for row in rows),
        total_unacknowledged_alerts=wa.unacknowledged_count(session),
        any_refresh_locked=any(row.refresh_locked for row in rows),
        watchlists=rows,
    )
