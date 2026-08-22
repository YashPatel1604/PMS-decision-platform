"""Export watchlist financial history matrix for baseline / gap analysis."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from pms_platform.fundamentals.catalog import COMPUTATION_VERSION
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.security_identity_alias import SecurityIdentityAlias
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.models.watchlist_member_metrics import WatchlistMemberMetrics
from pms_platform.watchlists.history_audit import classify_member_history
from pms_platform.watchlists.identity_link import is_canonically_linked
from pms_platform.watchlists.metric_diagnostics import bse_code


def export_financial_history_matrix(session: Session, path: Path) -> int:
    """Write one CSV row per canonically linked watchlist member."""
    members = session.scalars(
        select(WatchlistMember)
        .options(joinedload(WatchlistMember.security))
        .order_by(WatchlistMember.watchlist_id, WatchlistMember.member_id)
    ).all()
    path.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "security_id",
        "canonical_name",
        "display_name",
        "nse_symbol",
        "bse_code",
        "isin",
        "historical_aliases",
        "historical_nse_symbols",
        "historical_bse_codes",
        "historical_isins",
        "earliest_quarterly_period",
        "latest_quarterly_period",
        "quarterly_row_count",
        "earliest_annual_fy",
        "latest_annual_fy",
        "annual_row_count",
        "distinct_fiscal_years",
        "latest_filing_date",
        "cagr_missing_reason",
        "annual_quality_missing_reason",
    ]

    rows_written = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for member in members:
            if not is_canonically_linked(member):
                continue
            bse = bse_code(member)
            sec = member.security
            alias_rows = []
            if member.security_id:
                alias_rows = session.scalars(
                    select(SecurityIdentityAlias).where(
                        SecurityIdentityAlias.security_id == member.security_id
                    )
                ).all()

            hist_nse = sorted(
                {
                    r.historical_nse_symbol or (r.alias_value if r.alias_type == "NSE_SYMBOL" else "")
                    for r in alias_rows
                    if r.relationship_type == "RENAMED"
                    and (r.historical_nse_symbol or r.alias_type == "NSE_SYMBOL")
                }
                - {""}
            )
            hist_bse = sorted(
                {
                    r.historical_bse_code or (r.alias_value if r.alias_type == "BSE_CODE" else "")
                    for r in alias_rows
                    if r.relationship_type == "RENAMED"
                    and (r.historical_bse_code or r.alias_type == "BSE_CODE")
                }
                - {""}
            )
            hist_isin = sorted(
                {
                    r.historical_isin or (r.alias_value if r.alias_type == "ISIN" else "")
                    for r in alias_rows
                    if r.relationship_type == "RENAMED"
                    and (r.historical_isin or r.alias_type == "ISIN")
                }
                - {""}
            )
            hist_names = sorted(
                {r.alias_name for r in alias_rows if r.alias_type == "WATCHLIST_NAME" and r.alias_name}
            )

            q_earliest = q_latest = None
            q_count = 0
            latest_filing = None
            if bse:
                q_earliest = session.scalar(
                    select(func.min(CompanyFundamentalsQuarterly.period_end_date)).where(
                        CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                        CompanyFundamentalsQuarterly.identifier == bse,
                    )
                )
                q_latest = session.scalar(
                    select(func.max(CompanyFundamentalsQuarterly.period_end_date)).where(
                        CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                        CompanyFundamentalsQuarterly.identifier == bse,
                    )
                )
                q_count = session.scalar(
                    select(func.count())
                    .select_from(CompanyFundamentalsQuarterly)
                    .where(
                        CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                        CompanyFundamentalsQuarterly.identifier == bse,
                    )
                ) or 0
                latest_filing = session.scalar(
                    select(func.max(CompanyFundamentalsQuarterly.retrieved_at)).where(
                        CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
                        CompanyFundamentalsQuarterly.identifier == bse,
                    )
                )

            annual_fys: list[int] = []
            if bse:
                annual_fys = list(
                    session.scalars(
                        select(AnnualFundamentalsSnapshot.fiscal_year)
                        .where(
                            AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                            AnnualFundamentalsSnapshot.identifier == bse,
                        )
                        .order_by(AnnualFundamentalsSnapshot.fiscal_year)
                    ).all()
                )

            distinct_fy = 0
            if bse:
                distinct_fy = session.scalar(
                    select(func.count(func.distinct(FundamentalSnapshot.fiscal_year))).where(
                        FundamentalSnapshot.identifier_type == "BSE_CODE",
                        FundamentalSnapshot.identifier == bse,
                        FundamentalSnapshot.computation_version == COMPUTATION_VERSION,
                    )
                ) or 0

            gap = classify_member_history(session, member)
            cache = session.get(WatchlistMemberMetrics, member.member_id)
            cagr_reason = gap.cagr_5y_classification
            annual_reason = gap.annual_quality_classification
            if cache and isinstance(cache.diagnostics, dict):
                mr = cache.diagnostics.get("missing_reasons") or {}
                if not cagr_reason and mr.get("sales_5y_cagr"):
                    cagr_reason = mr["sales_5y_cagr"]
                if not annual_reason and mr.get("roe_pct"):
                    annual_reason = mr["roe_pct"]

            writer.writerow(
                {
                    "security_id": member.security_id,
                    "canonical_name": sec.canonical_name if sec else "",
                    "display_name": member.display_name,
                    "nse_symbol": member.nse_symbol or (sec.current_nse_symbol if sec else ""),
                    "bse_code": bse or "",
                    "isin": member.isin or (sec.isin if sec else ""),
                    "historical_aliases": "|".join(hist_names),
                    "historical_nse_symbols": "|".join(hist_nse),
                    "historical_bse_codes": "|".join(hist_bse),
                    "historical_isins": "|".join(hist_isin),
                    "earliest_quarterly_period": q_earliest.isoformat() if q_earliest else "",
                    "latest_quarterly_period": q_latest.isoformat() if q_latest else "",
                    "quarterly_row_count": q_count,
                    "earliest_annual_fy": min(annual_fys) if annual_fys else "",
                    "latest_annual_fy": max(annual_fys) if annual_fys else "",
                    "annual_row_count": len(annual_fys),
                    "distinct_fiscal_years": distinct_fy,
                    "latest_filing_date": latest_filing.isoformat() if latest_filing else "",
                    "cagr_missing_reason": cagr_reason or "",
                    "annual_quality_missing_reason": annual_reason or "",
                }
            )
            rows_written += 1
    return rows_written
