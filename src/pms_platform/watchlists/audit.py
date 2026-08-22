"""Watchlist data coverage audit and missing-reason diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from pms_platform.fundamentals.catalog import METRIC_CATALOG, WATCHLIST_METRICS_VERSION
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.models.watchlist_member_metrics import WatchlistMemberMetrics
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl
from pms_platform.watchlists.identity_link import (
    count_master_without_prices,
    count_prices_without_master,
    is_canonically_linked,
    linkage_status,
)
from pms_platform.watchlists.member_context import load_member_snapshot_context
from pms_platform.watchlists.metric_diagnostics import MissingReason, bse_code, diagnose_missing

__all__ = ["MissingReason", "audit_watchlist_data", "format_audit_report"]


@dataclass
class MetricCoverage:
    key: str
    label: str
    group: str
    filled: int
    missing: int
    applicable: int
    coverage_pct: float
    missing_by_reason: dict[str, int] = field(default_factory=dict)


@dataclass
class MemberAudit:
    member_id: int
    display_name: str
    watchlist_id: int
    watchlist_name: str
    resolution_status: str
    nse_symbol: str | None
    bse_code: str | None
    security_id: str | None
    price_rows: int
    quarterly_rows: int
    has_valuation: bool
    has_annual: bool
    has_promoter: bool
    has_cache: bool
    cache_stale_vs_snapshots: bool
    filled_metrics: int
    missing_metrics: int
    top_missing_reasons: dict[str, int] = field(default_factory=dict)


@dataclass
class WatchlistDataAuditReport:
    generated_at: datetime
    watchlist_id: int | None
    watchlist_name: str | None
    total_members: int
    resolved_members: int
    unresolved_members: int
    missing_nse: int
    missing_bse: int
    missing_security_id: int
    no_daily_prices: int
    insufficient_quarterly_history: int
    metrics_cache_stale_count: int
    overall_coverage_pct: float
    metric_coverage: tuple[MetricCoverage, ...]
    source_distribution: dict[str, int]
    members: tuple[MemberAudit, ...]
    sample_gaps: tuple[tuple[str, str, str], ...]  # display_name, metric, reason
    canonically_linked_members: int = 0
    exchange_resolved_members: int = 0
    ambiguous_identity_members: int = 0
    unsupported_members: int = 0
    missing_isin: int = 0
    inactive_or_delisted: int = 0
    prices_without_security_master: int = 0
    security_master_without_prices: int = 0


def audit_watchlist_data(
    session: Session,
    *,
    watchlist_id: int | None = None,
) -> WatchlistDataAuditReport:
    """Measure metric coverage and diagnose missing values for watchlist members."""
    all_keys = tuple(m.key for m in METRIC_CATALOG)
    watchlists = (
        [wl.get_watchlist(session, watchlist_id)]
        if watchlist_id is not None
        else wl.list_watchlists(session)
    )

    members: list[WatchlistMember] = []
    wl_names: dict[int, str] = {}
    for w in watchlists:
        wl_names[w.watchlist_id] = w.name
        members.extend(
            session.scalars(
                select(WatchlistMember)
                .where(WatchlistMember.watchlist_id == w.watchlist_id)
                .options(joinedload(WatchlistMember.security))
            ).all()
        )

    resolved = sum(1 for m in members if m.resolution_status == "RESOLVED")
    canonical = sum(1 for m in members if is_canonically_linked(m))
    exchange_only = sum(1 for m in members if linkage_status(m) == "EXCHANGE_RESOLVED")
    ambiguous = sum(1 for m in members if linkage_status(m) == "AMBIGUOUS")
    unsupported = sum(1 for m in members if linkage_status(m) == "UNSUPPORTED")
    missing_isin = sum(1 for m in members if is_canonically_linked(m) and not (m.isin or (m.security.isin if m.security else None)))
    inactive = sum(
        1
        for m in members
        if m.security and (m.security.status or "").upper() == "INACTIVE"
    )
    orphan_prices = count_prices_without_master(session)
    master_no_prices = count_master_without_prices(session)
    missing_nse = sum(1 for m in members if not (m.nse_symbol or "").strip())
    missing_bse = sum(1 for m in members if not bse_code(m))
    missing_sec = sum(1 for m in members if not m.security_id)
    no_prices = 0
    insuff_q = 0
    cache_stale = 0

    metric_filled: dict[str, int] = {k: 0 for k in all_keys}
    metric_missing: dict[str, int] = {k: 0 for k in all_keys}
    metric_reasons: dict[str, dict[str, int]] = {k: {} for k in all_keys}
    source_dist: dict[str, int] = {}
    member_audits: list[MemberAudit] = []
    sample_gaps: list[tuple[str, str, str]] = []

    # One screen join per watchlist (same read path as /screen, no external calls).
    metrics_by_member: dict[int, dict[str, Decimal | None]] = {}
    for w in watchlists:
        screen_rows = scr.assemble_screen_rows(session, w.watchlist_id, column_keys=all_keys)
        for row in screen_rows:
            metrics_by_member[row.member_id] = row.metrics

    for member in members:
        bse = bse_code(member)
        ctx = load_member_snapshot_context(session, member)
        price_rows = ctx.price_rows
        q_rows = ctx.quarterly_rows
        if member.resolution_status in {"RESOLVED", "EXCHANGE_RESOLVED"} and price_rows == 0:
            no_prices += 1
        if member.resolution_status in {"RESOLVED", "EXCHANGE_RESOLVED"} and q_rows < 8:
            insuff_q += 1

        has_val = ctx.has_val
        has_annual = ctx.has_annual
        has_prom = ctx.has_prom
        fund_row, val_row, annual_row, prom_row = (
            ctx.fund_row,
            ctx.val_row,
            ctx.annual_row,
            ctx.prom_row,
        )
        for prov in (
            fund_row.provider if fund_row else None,
            val_row.provider if val_row else None,
            annual_row.provider if annual_row else None,
            prom_row.provider if prom_row else None,
        ):
            if prov:
                source_dist[prov] = source_dist.get(prov, 0) + 1

        cache_row = session.get(WatchlistMemberMetrics, member.member_id)
        cached_reasons: dict[str, str] = {}
        if (
            cache_row
            and cache_row.computation_version == WATCHLIST_METRICS_VERSION
            and isinstance(cache_row.diagnostics, dict)
        ):
            cached_reasons = dict(cache_row.diagnostics.get("missing_reasons") or {})

        cache_stale_flag = False
        if cache_row and fund_row and cache_row.computed_at and fund_row.computed_at:
            cache_ts = cache_row.computed_at
            fund_ts = fund_row.computed_at
            if cache_ts.tzinfo is None:
                cache_ts = cache_ts.replace(tzinfo=timezone.utc)
            if fund_ts.tzinfo is None:
                fund_ts = fund_ts.replace(tzinfo=timezone.utc)
            if fund_ts > cache_ts:
                cache_stale_flag = True
                cache_stale += 1

        metrics = metrics_by_member.get(member.member_id, {k: None for k in all_keys})

        filled = missing = 0
        member_reasons: dict[str, int] = {}
        for key in all_keys:
            val = metrics.get(key)
            applicable = member.resolution_status in {"RESOLVED", "EXCHANGE_RESOLVED"}
            if not applicable:
                continue
            if val is not None:
                metric_filled[key] += 1
                filled += 1
                continue
            metric_missing[key] += 1
            missing += 1
            rs = cached_reasons.get(key)
            if not rs:
                reason = diagnose_missing(member=member, metric_key=key, value=val, ctx=ctx)
                rs = reason.value if reason else MissingReason.SOURCE_NOT_AVAILABLE.value
            metric_reasons[key][rs] = metric_reasons[key].get(rs, 0) + 1
            member_reasons[rs] = member_reasons.get(rs, 0) + 1
            if len(sample_gaps) < 40:
                sample_gaps.append((member.display_name, key, rs))

        member_audits.append(
            MemberAudit(
                member_id=member.member_id,
                display_name=member.display_name,
                watchlist_id=member.watchlist_id,
                watchlist_name=wl_names.get(member.watchlist_id, ""),
                resolution_status=member.resolution_status,
                nse_symbol=member.nse_symbol,
                bse_code=bse,
                security_id=member.security_id,
                price_rows=price_rows,
                quarterly_rows=q_rows,
                has_valuation=has_val,
                has_annual=has_annual,
                has_promoter=has_prom,
                has_cache=cache_row is not None,
                cache_stale_vs_snapshots=cache_stale_flag,
                filled_metrics=filled,
                missing_metrics=missing,
                top_missing_reasons=member_reasons,
            )
        )

    resolved_applicable = max(resolved + exchange_only, 1)
    total_cells = (resolved + exchange_only) * len(all_keys)
    filled_cells = sum(metric_filled.values())
    overall_pct = (100.0 * filled_cells / total_cells) if total_cells else 0.0

    metric_coverage = tuple(
        MetricCoverage(
            key=m.key,
            label=m.label,
            group=m.group,
            filled=metric_filled[m.key],
            missing=metric_missing[m.key],
            applicable=resolved + exchange_only,
            coverage_pct=round(100.0 * metric_filled[m.key] / resolved_applicable, 1),
            missing_by_reason=dict(sorted(metric_reasons[m.key].items())),
        )
        for m in METRIC_CATALOG
    )

    wl_label = watchlists[0].name if len(watchlists) == 1 else None
    wid = watchlists[0].watchlist_id if len(watchlists) == 1 else watchlist_id

    return WatchlistDataAuditReport(
        generated_at=datetime.now(timezone.utc),
        watchlist_id=wid,
        watchlist_name=wl_label,
        total_members=len(members),
        resolved_members=resolved,
        unresolved_members=len(members) - resolved,
        missing_nse=missing_nse,
        missing_bse=missing_bse,
        missing_security_id=missing_sec,
        no_daily_prices=no_prices,
        insufficient_quarterly_history=insuff_q,
        metrics_cache_stale_count=cache_stale,
        overall_coverage_pct=round(overall_pct, 1),
        metric_coverage=metric_coverage,
        source_distribution=dict(sorted(source_dist.items())),
        members=tuple(member_audits),
        sample_gaps=tuple(sample_gaps),
        canonically_linked_members=canonical,
        exchange_resolved_members=exchange_only,
        ambiguous_identity_members=ambiguous,
        unsupported_members=unsupported,
        missing_isin=missing_isin,
        inactive_or_delisted=inactive,
        prices_without_security_master=orphan_prices,
        security_master_without_prices=master_no_prices,
    )


def format_audit_report(report: WatchlistDataAuditReport) -> str:
    """Human-readable audit summary for CLI."""
    lines = [
        f"Watchlist data audit @ {report.generated_at.isoformat()}",
        f"Scope: {report.watchlist_name or 'ALL watchlists'} (id={report.watchlist_id})",
        "",
        "Members",
        f"  total={report.total_members} resolved={report.resolved_members} "
        f"unresolved={report.unresolved_members}",
        f"  missing NSE={report.missing_nse} BSE={report.missing_bse} "
        f"security_id={report.missing_security_id}",
        "Identity",
        f"  canonically_linked={report.canonically_linked_members} "
        f"exchange_resolved={report.exchange_resolved_members} "
        f"ambiguous={report.ambiguous_identity_members} "
        f"unsupported={report.unsupported_members}",
        f"  missing ISIN (linked)={report.missing_isin} "
        f"inactive/delisted={report.inactive_or_delisted}",
        f"  orphan daily_prices={report.prices_without_security_master} "
        f"master w/o prices={report.security_master_without_prices}",
        f"  no daily_prices (resolved+exchange)={report.no_daily_prices}",
        f"  insufficient quarterly history (<8 rows)={report.insufficient_quarterly_history}",
        f"  metrics cache older than snapshots={report.metrics_cache_stale_count}",
        f"  overall metric coverage={report.overall_coverage_pct}%",
        "",
        "Source distribution (snapshot providers seen)",
    ]
    for src, n in report.source_distribution.items():
        lines.append(f"  {src}: {n}")
    if not report.source_distribution:
        lines.append("  (none)")

    lines.extend(["", "Metric coverage (resolved members only)"])
    for mc in sorted(report.metric_coverage, key=lambda x: x.coverage_pct):
        reasons = ", ".join(f"{k}={v}" for k, v in mc.missing_by_reason.items()) or "—"
        lines.append(
            f"  [{mc.group}] {mc.label}: {mc.coverage_pct}% "
            f"({mc.filled}/{mc.applicable}) missing_reasons: {reasons}"
        )

    lines.extend(["", "Worst members by missing metrics"])
    worst = sorted(report.members, key=lambda m: -m.missing_metrics)[:15]
    for m in worst:
        if m.missing_metrics == 0:
            continue
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(m.top_missing_reasons.items())[:3])
        lines.append(
            f"  {m.display_name} ({m.watchlist_name}): missing={m.missing_metrics} "
            f"prices={m.price_rows} q_rows={m.quarterly_rows} val={m.has_valuation} "
            f"annual={m.has_annual} reasons: {reasons}"
        )

    if report.sample_gaps:
        lines.extend(["", "Sample gaps (name, metric, reason)"])
        for name, metric, reason in report.sample_gaps[:25]:
            lines.append(f"  {name} | {metric} | {reason}")

    return "\n".join(lines)
