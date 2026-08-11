"""Watchlist fundamentals screener service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from pms_platform.fundamentals.catalog import COMPUTATION_VERSION, METRIC_CATALOG, MetricDefinition
from pms_platform.market_data.bse_scrip_universe import resolve_bse_code
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.promoter_snapshot import PromoterSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import service as wl

STALE_AFTER_DAYS = 90

DEFAULT_COLUMNS: tuple[str, ...] = (
    "sales",
    "sales_yoy_pct",
    "opm",
    "pat_yoy_pct",
)

METRIC_KEYS: frozenset[str] = frozenset(metric.key for metric in METRIC_CATALOG)
SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    {
        "sales",
        "pat",
        "opm",
        "npm",
        "sales_yoy_pct",
        "sales_qoq_pct",
        "pat_yoy_pct",
        "opm_delta_pp",
        "npm_delta_pp",
        # Multi-year CAGR (populated after Phase 5)
        "sales_3y_cagr",
        "sales_5y_cagr",
        "pat_3y_cagr",
        "pat_5y_cagr",
    }
)

VALUATION_FIELDS: frozenset[str] = frozenset(
    {
        "market_cap_cr",
        "pe_ratio",
        "industry_pe",
        "price_to_book",
        "price_to_sales",
        "eps",
        "book_value_per_share",
        "dividend_yield",
        "earnings_yield",
        "peg_ratio",
        "week_52_high",
        "week_52_low",
        "return_1d_pct",
        "return_1m_pct",
        "return_3m_pct",
        "return_6m_pct",
        "return_1y_pct",
        "return_3y_pct",
        "all_time_high",
    }
)

PROMOTER_FIELDS: frozenset[str] = frozenset(
    {
        "promoter_holding_pct",
        "promoter_holding_change_pp",
        "pledged_pct",
    }
)

ANNUAL_FIELDS: frozenset[str] = frozenset(
    {
        "roce",
        "roe",
        "roa",
        "debt_to_equity",
        "interest_coverage",
        "current_ratio",
    }
)


@dataclass(frozen=True)
class ScreenRow:
    """One watchlist member joined with latest fundamentals snapshot."""

    member_id: int
    display_name: str
    nse_symbol: str | None
    bse_code: str | None
    security_id: str | None
    sector: str | None
    industry: str | None
    resolution_status: str
    fiscal_year: int | None
    fiscal_quarter: str | None
    period_end_date: object | None
    retrieved_at: datetime | None
    has_fundamentals: bool
    fundamentals_stale: bool
    metrics: dict[str, Decimal | None]


def list_metric_catalog() -> tuple[MetricDefinition, ...]:
    return METRIC_CATALOG


def parse_columns(columns: str | None) -> tuple[str, ...]:
    if not columns or not columns.strip():
        return DEFAULT_COLUMNS
    parsed = tuple(
        key.strip()
        for key in columns.split(",")
        if key.strip() in METRIC_KEYS
    )
    return parsed or DEFAULT_COLUMNS


def parse_sort(sort: str | None) -> tuple[str | None, str]:
    if not sort or not sort.strip():
        return None, "asc"
    if ":" in sort:
        column, direction = sort.rsplit(":", 1)
        column = column.strip()
        direction = direction.strip().lower()
    else:
        column = sort.strip()
        direction = "asc"
    if column not in METRIC_KEYS and column not in {"display_name", "period_end_date"}:
        return None, "asc"
    if direction not in {"asc", "desc"}:
        direction = "asc"
    return column, direction


def _member_keys(member: WatchlistMember) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    if member.security_id:
        keys.append(("SECURITY_ID", member.security_id))
    if member.nse_symbol:
        keys.append(("NSE_SYMBOL", member.nse_symbol.strip().upper()))
    if member.bse_code:
        keys.append(("BSE_CODE", member.bse_code.strip()))
    live_bse = resolve_bse_code(
        nse_symbol=member.nse_symbol,
        company_name=member.display_name,
        isin=member.isin,
    )
    if live_bse:
        keys.append(("BSE_CODE", live_bse.strip()))
    if member.display_name:
        keys.append(("PORTFOLIO_NAME", member.display_name.strip()))
    return keys


def _index_latest_snapshots(
    snapshots: list[FundamentalSnapshot],
) -> dict[tuple[str, str], FundamentalSnapshot]:
    latest: dict[tuple[str, str], FundamentalSnapshot] = {}
    for row in snapshots:
        key = (row.identifier_type, row.identifier)
        existing = latest.get(key)
        if existing is None or row.period_end_date > existing.period_end_date:
            latest[key] = row
    return latest


def _find_snapshot(
    member: WatchlistMember,
    latest_by_key: dict[tuple[str, str], FundamentalSnapshot],
) -> FundamentalSnapshot | None:
    for key in _member_keys(member):
        hit = latest_by_key.get(key)
        if hit is not None:
            return hit
    return None


def _is_stale(retrieved_at: datetime | None, *, now: datetime | None = None) -> bool:
    if retrieved_at is None:
        return True
    clock = now or datetime.now(timezone.utc)
    ts = retrieved_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return clock - ts > timedelta(days=STALE_AFTER_DAYS)


def _metric_values(
    snapshot: FundamentalSnapshot | None,
    valuation: ValuationSnapshot | None,
    promoter: Any | None,
    annual: Any | None,
    columns: tuple[str, ...],
) -> dict[str, Decimal | None]:
    values: dict[str, Decimal | None] = {}
    for column in columns:
        if column in SNAPSHOT_FIELDS:
            src: Any = snapshot
        elif column in VALUATION_FIELDS:
            src = valuation
        elif column in PROMOTER_FIELDS:
            src = promoter
        elif column in ANNUAL_FIELDS:
            src = annual
        else:
            src = None
        raw = getattr(src, column, None) if src is not None else None
        values[column] = raw if isinstance(raw, Decimal) or raw is None else Decimal(str(raw))
    return values


def _sort_value(row: ScreenRow, column: str) -> Any:
    if column == "display_name":
        return row.display_name.casefold()
    if column == "period_end_date":
        return row.period_end_date or ""
    return row.metrics.get(column)


def sort_screen_rows(
    rows: list[ScreenRow],
    *,
    column: str | None,
    direction: str,
) -> list[ScreenRow]:
    if column is None:
        return rows

    def key(row: ScreenRow) -> tuple[int, Any]:
        value = _sort_value(row, column)
        if value is None or value == "":
            return (1, 0)
        if isinstance(value, Decimal):
            num = float(value)
            return (0, -num if direction == "desc" else num)
        if direction == "desc":
            return (0, _invert_sortable(value))
        return (0, value)

    return sorted(rows, key=key)


def _invert_sortable(value: Any) -> Any:
    if isinstance(value, str):
        return tuple(-ord(ch) for ch in value.casefold())
    return value


def _index_latest_valuations(
    rows: list[ValuationSnapshot],
) -> dict[tuple[str, str], ValuationSnapshot]:
    latest: dict[tuple[str, str], ValuationSnapshot] = {}
    for row in rows:
        key = (row.identifier_type, row.identifier)
        existing = latest.get(key)
        if existing is None or row.as_of_date > existing.as_of_date:
            latest[key] = row
    return latest


def _find_valuation(
    member: WatchlistMember,
    latest_by_key: dict[tuple[str, str], ValuationSnapshot],
) -> ValuationSnapshot | None:
    for key in _member_keys(member):
        hit = latest_by_key.get(key)
        if hit is not None:
            return hit
    return None


def _index_latest_annual(
    rows: list[AnnualFundamentalsSnapshot],
) -> dict[tuple[str, str], AnnualFundamentalsSnapshot]:
    latest: dict[tuple[str, str], AnnualFundamentalsSnapshot] = {}
    for row in rows:
        key = (row.identifier_type, row.identifier)
        existing = latest.get(key)
        if existing is None or row.fiscal_year > existing.fiscal_year:
            latest[key] = row
    return latest


def _index_latest_promoter(
    rows: list[PromoterSnapshot],
) -> dict[tuple[str, str], PromoterSnapshot]:
    latest: dict[tuple[str, str], PromoterSnapshot] = {}
    for row in rows:
        key = (row.identifier_type, row.identifier)
        existing = latest.get(key)
        if existing is None or row.quarter_end_date > existing.quarter_end_date:
            latest[key] = row
    return latest


def _member_bse_codes(members: list[WatchlistMember]) -> list[str]:
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


_VALUATION_FRESH_HOURS = 6


def _valuation_needs_refresh(row: ValuationSnapshot | None) -> bool:
    if row is None:
        return True
    # Hollow rows are useless — force a re-fetch.
    if row.market_cap_cr is None and row.pe_ratio is None:
        return True
    if row.as_of_date == date.today():
        return False
    computed = row.computed_at
    if computed is not None:
        if computed.tzinfo is None:
            computed = computed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - computed
        if age <= timedelta(hours=_VALUATION_FRESH_HOURS):
            return False
    return True


def _promoter_needs_refresh(row: PromoterSnapshot | None) -> bool:
    if row is None:
        return True
    return row.promoter_holding_pct is None and row.pledged_pct is None


def ensure_screen_metrics(
    session: Session,
    members: list[WatchlistMember],
    column_keys: tuple[str, ...],
) -> None:
    """Fetch and persist missing valuation/promoter metrics for visible columns.

    Called on screener load so newly selected columns populate without a full
    watchlist refresh.
    """
    need_valuation = any(col in VALUATION_FIELDS for col in column_keys)
    need_promoter = any(col in PROMOTER_FIELDS for col in column_keys)
    need_annual = any(col in ANNUAL_FIELDS for col in column_keys)
    if not (need_valuation or need_promoter or need_annual):
        return

    codes = _member_bse_codes(members)
    if not codes:
        return

    missing: list[str] = []
    missing_p: list[str] = []

    if need_valuation:
        valuations = session.scalars(select(ValuationSnapshot)).all()
        latest = _index_latest_valuations(list(valuations))
        missing = [
            code
            for code in codes
            if _valuation_needs_refresh(latest.get(("BSE_CODE", code)))
        ]

    if need_promoter:
        promoters = session.scalars(select(PromoterSnapshot)).all()
        latest_p = _index_latest_promoter(list(promoters))
        missing_p = [
            code
            for code in codes
            if _promoter_needs_refresh(latest_p.get(("BSE_CODE", code)))
        ]

    # Valuation + promoter in parallel via their own worker pools; run sequentially
    # here only to keep Session writes single-threaded.
    if missing:
        try:
            from pms_platform.fundamentals.providers.valuation import (
                refresh_valuation_snapshots,
            )

            refresh_valuation_snapshots(session, missing, force=False)
            session.flush()
        except Exception:
            pass

    if missing_p:
        try:
            from pms_platform.fundamentals.providers.promoter import (
                refresh_promoter_snapshots,
            )

            refresh_promoter_snapshots(session, missing_p)
            session.flush()
        except Exception:
            pass

    if need_valuation:
        need_returns = any(
            col.startswith("return_") or col == "all_time_high" for col in column_keys
        )
        if need_returns:
            try:
                from pms_platform.market_data.price_returns import refresh_price_returns

                refresh_price_returns(
                    session,
                    [("BSE_CODE", code) for code in codes],
                )
                session.flush()
            except Exception:
                pass

    if need_annual:
        annual_rows = session.scalars(select(AnnualFundamentalsSnapshot)).all()
        latest_a = _index_latest_annual(list(annual_rows))
        missing_a = [
            code
            for code in codes
            if latest_a.get(("BSE_CODE", code)) is None
            or (
                latest_a[("BSE_CODE", code)].current_ratio is None
                and latest_a[("BSE_CODE", code)].roce is None
                and latest_a[("BSE_CODE", code)].roe is None
            )
        ]
        if missing_a:
            try:
                from pms_platform.fundamentals.providers.annual_xbrl import (
                    refresh_annual_fundamentals,
                )

                refresh_annual_fundamentals(
                    session,
                    missing_a[:8],
                    years_back=1,
                    request_delay_sec=0.3,
                )
                session.flush()
            except Exception:
                pass


def build_watchlist_screen(
    session: Session,
    watchlist_id: int,
    *,
    columns: str | None = None,
    sort: str | None = None,
    computation_version: str = COMPUTATION_VERSION,
) -> list[ScreenRow]:
    """Build screener rows for a watchlist with optional column filter and sort."""
    wl.get_watchlist(session, watchlist_id)
    column_keys = parse_columns(columns)
    sort_column, sort_direction = parse_sort(sort)

    members = list(
        session.scalars(
            select(WatchlistMember)
            .where(WatchlistMember.watchlist_id == watchlist_id)
            .options(joinedload(WatchlistMember.security))
            .order_by(WatchlistMember.display_name)
        ).all()
    )

    ensure_screen_metrics(session, members, column_keys)

    snapshots = session.scalars(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.computation_version == computation_version
        )
    ).all()
    latest_by_key = _index_latest_snapshots(list(snapshots))

    valuations = session.scalars(select(ValuationSnapshot)).all()
    latest_valuation_by_key = _index_latest_valuations(list(valuations))

    promoter_rows = session.scalars(select(PromoterSnapshot)).all()
    promoter_by_key = _index_latest_promoter(list(promoter_rows))

    annual_rows = session.scalars(select(AnnualFundamentalsSnapshot)).all()
    annual_by_key = _index_latest_annual(list(annual_rows))

    rows: list[ScreenRow] = []
    for member in members:
        snapshot = _find_snapshot(member, latest_by_key)
        valuation = _find_valuation(member, latest_valuation_by_key)
        promoter = _find_from_dict(member, promoter_by_key)
        annual = _find_from_dict(member, annual_by_key)
        sec = member.security
        rows.append(
            ScreenRow(
                member_id=member.member_id,
                display_name=member.display_name,
                nse_symbol=member.nse_symbol,
                bse_code=member.bse_code,
                security_id=member.security_id,
                sector=sec.sector if sec else None,
                industry=sec.industry if sec else None,
                resolution_status=member.resolution_status,
                fiscal_year=snapshot.fiscal_year if snapshot else None,
                fiscal_quarter=snapshot.fiscal_quarter if snapshot else None,
                period_end_date=snapshot.period_end_date if snapshot else None,
                retrieved_at=snapshot.retrieved_at if snapshot else None,
                has_fundamentals=snapshot is not None,
                fundamentals_stale=_is_stale(snapshot.retrieved_at if snapshot else None),
                metrics=_metric_values(snapshot, valuation, promoter, annual, column_keys),
            )
        )

    return sort_screen_rows(rows, column=sort_column, direction=sort_direction)


def _find_from_dict(
    member: WatchlistMember,
    by_key: dict[tuple[str, str], Any],
) -> Any | None:
    for key in _member_keys(member):
        hit = by_key.get(key)
        if hit is not None:
            return hit
    return None


def screen_rows_to_csv(rows: list[ScreenRow], columns: tuple[str, ...]) -> str:
    """Serialize screen rows to CSV for export."""
    import csv
    from io import StringIO

    catalog = {metric.key: metric.label for metric in METRIC_CATALOG}
    header = ["Company", "NSE", "BSE", "Quarter", "Period end", "Stale"]
    header.extend(catalog.get(col, col) for col in columns)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        quarter = (
            f"{row.fiscal_quarter}FY{str(row.fiscal_year)[-2:]}"
            if row.fiscal_year and row.fiscal_quarter
            else ""
        )
        line = [
            row.display_name,
            row.nse_symbol or "",
            row.bse_code or "",
            quarter,
            row.period_end_date.isoformat() if row.period_end_date else "",
            "yes" if row.fundamentals_stale else "no",
        ]
        for col in columns:
            val = row.metrics.get(col)
            line.append("" if val is None else str(val))
        writer.writerow(line)
    return buffer.getvalue()
