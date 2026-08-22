"""Annual FY-endpoint CAGR (5Y Sales/PAT from audited annual history)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.compute import compute_cagr
from pms_platform.market_data.bse_financial_results import fiscal_label
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists.identity_link import price_history_summary


@dataclass(frozen=True)
class AnnualEndpoint:
    fiscal_year: int
    period_end: date
    sales: Decimal | None
    pat: Decimal | None
    source: str


@dataclass(frozen=True)
class AnnualCagrResult:
    sales_5y_cagr: Decimal | None
    pat_5y_cagr: Decimal | None
    latest_fy: int | None
    base_fy: int | None
    latest_period_end: date | None
    base_period_end: date | None
    latest_sales: Decimal | None
    base_sales: Decimal | None
    latest_pat: Decimal | None
    base_pat: Decimal | None


def _annual_rows(session: Session, bse_code: str) -> list[AnnualFundamentalsSnapshot]:
    return list(
        session.scalars(
            select(AnnualFundamentalsSnapshot)
            .where(
                AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                AnnualFundamentalsSnapshot.identifier == bse_code,
            )
            .order_by(AnnualFundamentalsSnapshot.fiscal_year)
        ).all()
    )


def _fy_from_period_end(period_end: date) -> int:
    fy, _ = fiscal_label(period_end)
    return fy


def _q4_fallback(
    session: Session,
    bse_code: str,
    *,
    fiscal_year: int | None = None,
    period_end: date | None = None,
) -> tuple[Decimal | None, Decimal | None]:
    """Use full-year (Q4 / Mar) quarterly row when annual P&L columns are empty."""
    q = select(CompanyFundamentalsQuarterly).where(
        CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
        CompanyFundamentalsQuarterly.identifier == bse_code,
    )
    if period_end is not None:
        q = q.where(CompanyFundamentalsQuarterly.period_end_date == period_end)
    elif fiscal_year is not None:
        q = q.where(CompanyFundamentalsQuarterly.fiscal_year == fiscal_year)
    else:
        return None, None
    rows = session.scalars(q.order_by(CompanyFundamentalsQuarterly.period_end_date.desc())).all()
    if not rows:
        return None, None
    for row in rows:
        if row.fiscal_quarter in {"Q4", "FY"} or (row.period_end_date and row.period_end_date.month == 3):
            return row.sales, row.pat
    return rows[0].sales, rows[0].pat


def annual_endpoint(
    session: Session,
    bse_code: str,
    fiscal_year: int,
    *,
    annual_by_fy: dict[int, AnnualFundamentalsSnapshot] | None = None,
    period_end: date | None = None,
) -> AnnualEndpoint | None:
    row = (annual_by_fy or {}).get(fiscal_year)
    if row is None and period_end is not None:
        row = session.scalar(
            select(AnnualFundamentalsSnapshot).where(
                AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                AnnualFundamentalsSnapshot.identifier == bse_code,
                AnnualFundamentalsSnapshot.period_end_date == period_end,
            )
        )
    if row is None:
        row = session.scalar(
            select(AnnualFundamentalsSnapshot).where(
                AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                AnnualFundamentalsSnapshot.identifier == bse_code,
                AnnualFundamentalsSnapshot.fiscal_year == fiscal_year,
            )
        )
    sales = row.sales if row else None
    pat = row.pat if row else None
    source = row.provider if row else "none"
    q4_bse = row.identifier if row else bse_code
    pe = period_end or (row.period_end_date if row else None)
    if sales is None or pat is None:
        q_sales, q_pat = _q4_fallback(session, q4_bse, fiscal_year=fiscal_year, period_end=pe)
        if (sales is None or pat is None) and q4_bse != bse_code:
            q2_sales, q2_pat = _q4_fallback(session, bse_code, fiscal_year=fiscal_year, period_end=pe)
            if q_sales is None:
                q_sales = q2_sales
            if q_pat is None:
                q_pat = q2_pat
        if sales is None:
            sales = q_sales
        if pat is None:
            pat = q_pat
        if q_sales is not None or q_pat is not None:
            source = "quarterly_q4_fallback"
    if sales is None and pat is None:
        return None
    resolved_pe = pe or date(fiscal_year + 1, 3, 31)
    return AnnualEndpoint(
        fiscal_year=fiscal_year,
        period_end=resolved_pe,
        sales=sales,
        pat=pat,
        source=source,
    )


def _annual_rows_for_codes(session: Session, bse_codes: tuple[str, ...]) -> dict[int, AnnualFundamentalsSnapshot]:
    """Merge annual rows across canonical + historical BSE codes (best row per FY)."""
    merged: dict[int, AnnualFundamentalsSnapshot] = {}
    for code in bse_codes:
        if not code:
            continue
        for row in _annual_rows(session, code):
            existing = merged.get(row.fiscal_year)
            if existing is None:
                merged[row.fiscal_year] = row
                continue
            if existing.sales is None and row.sales is not None:
                merged[row.fiscal_year] = row
            elif existing.pat is None and row.pat is not None:
                merged[row.fiscal_year] = row
    return merged


def _march_period_ends(session: Session, bse_codes: tuple[str, ...]) -> list[date]:
    """All March year-end dates from annual snapshots + Q4 quarterly rows."""
    ends: set[date] = set()
    for code in bse_codes:
        if not code:
            continue
        for row in _annual_rows(session, code):
            if row.period_end_date and row.period_end_date.month == 3:
                ends.add(row.period_end_date)
        q_rows = session.scalars(
            select(CompanyFundamentalsQuarterly.period_end_date).where(
                CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                CompanyFundamentalsQuarterly.identifier == code,
                CompanyFundamentalsQuarterly.fiscal_quarter.in_(("Q4", "FY")),
            )
        ).all()
        for pe in q_rows:
            if pe and pe.month == 3:
                ends.add(pe)
    return sorted(ends)


def required_cagr_period_ends(
    session: Session,
    bse_code: str,
    *,
    extra_bse_codes: tuple[str, ...] = (),
) -> tuple[date | None, date | None]:
    """Latest March FY-end and base March FY-end (latest − 5 calendar years)."""
    codes = tuple(dict.fromkeys([bse_code, *extra_bse_codes]))
    march_ends = _march_period_ends(session, codes)
    if not march_ends:
        return None, None
    latest = march_ends[-1]
    base = date(latest.year - 5, 3, 31)
    return latest, base


def compute_annual_5y_cagr(
    session: Session,
    bse_code: str,
    *,
    extra_bse_codes: tuple[str, ...] = (),
) -> AnnualCagrResult:
    """March FY_latest vs March FY_latest−5 annual Sales/PAT CAGR."""
    codes = tuple(dict.fromkeys([bse_code, *extra_bse_codes]))
    by_fy = _annual_rows_for_codes(session, codes)
    latest_pe, base_pe = required_cagr_period_ends(session, bse_code, extra_bse_codes=extra_bse_codes)
    if latest_pe is None or base_pe is None:
        return AnnualCagrResult(None, None, None, None, None, None, None, None, None, None)

    latest_fy = _fy_from_period_end(latest_pe)
    base_fy = _fy_from_period_end(base_pe)
    latest = annual_endpoint(
        session,
        bse_code,
        latest_fy,
        annual_by_fy=by_fy,
        period_end=latest_pe,
    )
    base = annual_endpoint(
        session,
        bse_code,
        base_fy,
        annual_by_fy=by_fy,
        period_end=base_pe,
    )
    if latest is None or base is None:
        return AnnualCagrResult(
            None,
            None,
            latest_fy,
            base_fy,
            latest_pe,
            base_pe,
            latest.sales if latest else None,
            base.sales if base else None,
            latest.pat if latest else None,
            base.pat if base else None,
        )

    return AnnualCagrResult(
        sales_5y_cagr=compute_cagr(latest.sales, base.sales, 5),
        pat_5y_cagr=compute_cagr(latest.pat, base.pat, 5),
        latest_fy=latest_fy,
        base_fy=base_fy,
        latest_period_end=latest_pe,
        base_period_end=base_pe,
        latest_sales=latest.sales,
        base_sales=base.sales,
        latest_pat=latest.pat,
        base_pat=base.pat,
    )


def missing_fiscal_years_for_5y(session: Session, bse_code: str, *, years_back: int = 8) -> list[int]:
    """FY labels for latest/base CAGR endpoints still missing sales or PAT."""
    latest_pe, base_pe = required_cagr_period_ends(session, bse_code)
    if latest_pe is None:
        return []
    missing: list[int] = []
    for pe in (latest_pe, base_pe):
        if pe is None:
            continue
        fy = _fy_from_period_end(pe)
        floor = _fy_from_period_end(date(latest_pe.year - years_back, 3, 31))
        if fy < floor:
            continue
        ep = annual_endpoint(session, bse_code, fy, period_end=pe)
        if ep is None or (ep.sales is None and ep.pat is None):
            missing.append(fy)
    return sorted(set(missing))


def diagnose_5y_cagr_missing(
    session: Session,
    member: WatchlistMember,
    bse: str | None,
    result: AnnualCagrResult,
) -> str:
    """Specific missing reason for 5Y CAGR nulls."""
    from pms_platform.watchlists.metric_diagnostics import MissingReason

    if not bse:
        return MissingReason.NO_EXCHANGE_IDENTIFIER.value
    if member.resolution_status in {"UNSUPPORTED", "PENDING", "FAILED", "AMBIGUOUS"}:
        return MissingReason.UNRESOLVED_SECURITY.value

    ph = price_history_summary(session, member)
    span = int(ph.get("span_days") or 0)
    if span and span < 365 * 6 and result.latest_period_end is None:
        return MissingReason.TRUE_INSUFFICIENT_LISTING_HISTORY.value

    if result.latest_period_end is None:
        return MissingReason.ANNUAL_SOURCE_UNAVAILABLE.value
    if result.base_period_end is None:
        return MissingReason.ANNUAL_SOURCE_UNAVAILABLE.value

    base = annual_endpoint(
        session,
        bse,
        result.base_fy or _fy_from_period_end(result.base_period_end),
        period_end=result.base_period_end,
    )
    if base is None:
        if span and span < 365 * 6:
            return MissingReason.TRUE_INSUFFICIENT_LISTING_HISTORY.value
        return MissingReason.ANNUAL_REPORT_NOT_FOUND.value

    latest = annual_endpoint(
        session,
        bse,
        result.latest_fy or _fy_from_period_end(result.latest_period_end),
        period_end=result.latest_period_end,
    )
    if latest is None:
        return MissingReason.ANNUAL_SOURCE_UNAVAILABLE.value

    if result.base_sales is not None and result.base_sales <= 0:
        return MissingReason.INVALID_CAGR_BASE.value
    if result.base_pat is not None and result.base_pat <= 0:
        return MissingReason.INVALID_CAGR_BASE.value

    return MissingReason.ANNUAL_SOURCE_UNAVAILABLE.value
