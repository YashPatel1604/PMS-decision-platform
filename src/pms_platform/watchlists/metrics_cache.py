"""Rebuild materialized watchlist_member_metrics from snapshot tables."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from pms_platform.fundamentals.catalog import METRIC_CATALOG, WATCHLIST_METRICS_VERSION
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.models.watchlist_member_metrics import WatchlistMemberMetrics
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl
from pms_platform.watchlists.member_context import load_member_snapshot_context
from pms_platform.watchlists.metric_diagnostics import build_member_diagnostics


def _metrics_to_json(metrics: dict[str, Decimal | None]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, value in metrics.items():
        out[key] = float(value) if value is not None else None
    return out


def _json_to_metrics(raw: dict[str, object]) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for key, value in raw.items():
        if value is None:
            out[key] = None
        else:
            out[key] = Decimal(str(value))
    return out


def rebuild_watchlist_metrics(
    session: Session,
    watchlist_id: int,
    *,
    computation_version: str = WATCHLIST_METRICS_VERSION,
) -> int:
    """Recompute and persist materialized metrics for every member in a watchlist."""
    wl.get_watchlist(session, watchlist_id)
    all_columns = tuple(metric.key for metric in METRIC_CATALOG)
    rows = scr.assemble_screen_rows(
        session,
        watchlist_id,
        column_keys=all_columns,
    )
    members = {
        m.member_id: m
        for m in session.scalars(
            select(WatchlistMember).where(WatchlistMember.watchlist_id == watchlist_id)
        ).all()
    }

    session.execute(
        delete(WatchlistMemberMetrics).where(
            WatchlistMemberMetrics.watchlist_id == watchlist_id,
        )
    )

    now = datetime.now(timezone.utc)
    for row in rows:
        member = members.get(row.member_id)
        diagnostics: dict[str, object] = {}
        if member is not None:
            ctx = load_member_snapshot_context(session, member)
            diagnostics = build_member_diagnostics(
                session,
                member,
                row.metrics,
                ctx,
                computation_version=computation_version,
                metric_keys=all_columns,
            )
        session.add(
            WatchlistMemberMetrics(
                member_id=row.member_id,
                watchlist_id=watchlist_id,
                computation_version=computation_version,
                fiscal_year=row.fiscal_year,
                fiscal_quarter=row.fiscal_quarter,
                period_end_date=row.period_end_date,  # type: ignore[arg-type]
                retrieved_at=row.retrieved_at,
                has_fundamentals=row.has_fundamentals,
                fundamentals_stale=row.fundamentals_stale,
                metrics=_metrics_to_json(row.metrics),
                diagnostics=diagnostics,
                computed_at=now,
            )
        )
    session.flush()
    return len(rows)


def rebuild_all_watchlist_metrics(
    session: Session,
    *,
    computation_version: str = WATCHLIST_METRICS_VERSION,
) -> int:
    """Rebuild materialized metrics for every watchlist."""
    total = 0
    for watchlist in wl.list_watchlists(session):
        total += rebuild_watchlist_metrics(
            session,
            watchlist.watchlist_id,
            computation_version=computation_version,
        )
    return total


def load_cached_screen_rows(
    session: Session,
    watchlist_id: int,
    *,
    column_keys: tuple[str, ...],
    computation_version: str = WATCHLIST_METRICS_VERSION,
) -> list[scr.ScreenRow] | None:
    """Return screener rows from materialized cache, or None if cache is incomplete."""
    members = list(
        session.scalars(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .options(joinedload(WatchlistMember.security))
            .order_by(WatchlistMember.display_name)
        ).all()
    )
    if not members:
        return []

    cached = session.scalars(
        select(WatchlistMemberMetrics).where(
            WatchlistMemberMetrics.watchlist_id == watchlist_id,
            WatchlistMemberMetrics.computation_version == computation_version,
        )
    ).all()
    by_member = {row.member_id: row for row in cached}
    if len(by_member) < len(members):
        return None

    rows: list[scr.ScreenRow] = []
    for member in members:
        hit = by_member.get(member.member_id)
        if hit is None:
            return None
        full_metrics = _json_to_metrics(hit.metrics)
        sec = member.security
        rows.append(
            scr.ScreenRow(
                member_id=member.member_id,
                display_name=member.display_name,
                nse_symbol=member.nse_symbol,
                bse_code=member.bse_code,
                security_id=member.security_id,
                sector=sec.sector if sec else None,
                industry=sec.industry if sec else None,
                resolution_status=member.resolution_status,
                fiscal_year=hit.fiscal_year,
                fiscal_quarter=hit.fiscal_quarter,
                period_end_date=hit.period_end_date,
                retrieved_at=hit.retrieved_at,
                has_fundamentals=hit.has_fundamentals,
                fundamentals_stale=hit.fundamentals_stale,
                metrics={key: full_metrics.get(key) for key in column_keys},
            )
        )
    return rows
