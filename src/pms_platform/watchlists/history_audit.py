"""Classify INSUFFICIENT_HISTORY and annual-quality gaps with evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.fundamentals.catalog import COMPUTATION_VERSION
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.security_identity_alias import SecurityIdentityAlias
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists.financial_discovery import (
    FinancialDiscoveryIdentitySet,
    build_financial_discovery_identities,
)
from pms_platform.watchlists.metric_diagnostics import bse_code
from pms_platform.watchlists.identity_link import price_history_summary

CAGR_HISTORY_CLASS = (
    "TRUE_INSUFFICIENT_LISTING_HISTORY",
    "HISTORICAL_ALIAS_NOT_INGESTED",
    "CURRENT_SYMBOL_HISTORY_NOT_INGESTED",
    "LEGACY_NSE_HISTORY_NOT_INGESTED",
    "BSE_HISTORY_NOT_INGESTED",
    "NO_HISTORICAL_FILINGS_FOUND",
    "PARSER_GAP",
    "ANNUAL_EXTRACTION_GAP",
    "PERIOD_NORMALIZATION_GAP",
    "NEGATIVE_BASE_VALUE",
    "SOURCE_UNAVAILABLE",
)

ANNUAL_QUALITY_CLASS = (
    "TRUE_NO_ANNUAL_SOURCE",
    "HISTORICAL_ALIAS_NOT_INGESTED",
    "CURRENT_SYMBOL_HISTORY_NOT_INGESTED",
    "ANNUAL_PARSER_GAP",
    "MARCH_YEAR_NOT_INGESTED",
    "NO_HISTORICAL_FILINGS_FOUND",
    "SOURCE_UNAVAILABLE",
)


@dataclass(frozen=True)
class HistoryGapReport:
    member_id: int
    display_name: str
    security_id: str | None
    bse_code: str | None
    annual_row_count: int
    quarterly_row_count: int
    distinct_fiscal_years: int
    annual_first_fy: int | None
    annual_last_fy: int | None
    price_span_days: int
    cagr_5y_classification: str | None
    cagr_5y_base_fy_required: int | None
    cagr_5y_base_fy_available: bool
    annual_quality_classification: str | None
    verified_historical_aliases: tuple[str, ...]
    alias_identifiers: tuple[str, ...]


def _annual_years(session: Session, bse: str) -> list[int]:
    return list(
        session.scalars(
            select(AnnualFundamentalsSnapshot.fiscal_year)
            .where(
                AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                AnnualFundamentalsSnapshot.identifier == bse,
            )
            .order_by(AnnualFundamentalsSnapshot.fiscal_year)
        ).all()
    )


def _quarterly_stats(session: Session, bse: str) -> tuple[int, int]:
    row_count = session.scalar(
        select(func.count())
        .select_from(CompanyFundamentalsQuarterly)
        .where(
            CompanyFundamentalsQuarterly.identifier_type == "BSE_CODE",
            CompanyFundamentalsQuarterly.identifier == bse,
        )
    ) or 0
    distinct_fy = session.scalar(
        select(func.count(func.distinct(FundamentalSnapshot.fiscal_year))).where(
            FundamentalSnapshot.identifier_type == "BSE_CODE",
            FundamentalSnapshot.identifier == bse,
            FundamentalSnapshot.computation_version == COMPUTATION_VERSION,
        )
    ) or 0
    return int(row_count), int(distinct_fy)


def _verified_rename_aliases(session: Session, security_id: str) -> list[SecurityIdentityAlias]:
    return list(
        session.scalars(
            select(SecurityIdentityAlias).where(
                SecurityIdentityAlias.security_id == security_id,
                SecurityIdentityAlias.relationship_type == "RENAMED",
            )
        ).all()
    )


def _has_quarterly_for_identifier(
    session: Session,
    identifier_type: str,
    identifier: str,
) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(CompanyFundamentalsQuarterly)
            .where(
                CompanyFundamentalsQuarterly.identifier_type == identifier_type,
                CompanyFundamentalsQuarterly.identifier == identifier,
            )
        )
    )


def _has_annual_for_identifier(
    session: Session,
    identifier_type: str,
    identifier: str,
) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(AnnualFundamentalsSnapshot)
            .where(
                AnnualFundamentalsSnapshot.identifier_type == identifier_type,
                AnnualFundamentalsSnapshot.identifier == identifier,
            )
        )
    )


def _alias_covers_missing_years(
    session: Session,
    alias: SecurityIdentityAlias,
    *,
    required_fy: int | None,
) -> bool:
    """True when alias historical identifiers have filings but current BSE does not."""
    if required_fy is None:
        return False
    historical_ids: list[tuple[str, str]] = []
    if alias.historical_bse_code:
        historical_ids.append(("BSE_CODE", alias.historical_bse_code))
    if alias.historical_nse_symbol:
        historical_ids.append(("NSE_SYMBOL", alias.historical_nse_symbol))
    for id_type, id_value in historical_ids:
        if id_type == "BSE_CODE":
            years = _annual_years(session, id_value)
            if required_fy in years:
                return True
            if _has_quarterly_for_identifier(session, id_type, id_value):
                return True
    return False


def _classify_cagr_gap(
    session: Session,
    member: WatchlistMember,
    *,
    bse: str | None,
    years: list[int],
    q_count: int,
    distinct_fy: int,
    span_days: int,
    latest_fy: int | None,
    base_required: int | None,
    base_available: bool,
    identities: FinancialDiscoveryIdentitySet | None,
) -> str | None:
    if not bse:
        return "SOURCE_UNAVAILABLE"

    if latest_fy is None:
        if q_count == 0:
            if identities and identities.historical_nse_symbols:
                return "HISTORICAL_ALIAS_NOT_INGESTED"
            if member.nse_symbol:
                return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"
            return "BSE_HISTORY_NOT_INGESTED"
        if distinct_fy >= 6:
            return "PERIOD_NORMALIZATION_GAP"
        return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"

    if base_available:
        return None

    if span_days < 365 * 5:
        return "TRUE_INSUFFICIENT_LISTING_HISTORY"

    if member.security_id:
        aliases = _verified_rename_aliases(session, member.security_id)
        for alias in aliases:
            if _alias_covers_missing_years(session, alias, required_fy=base_required):
                return "HISTORICAL_ALIAS_NOT_INGESTED"

    if q_count >= 12 and distinct_fy >= 4:
        if distinct_fy < 6:
            if span_days < 365 * 6:
                return "TRUE_INSUFFICIENT_LISTING_HISTORY"
            return "NO_HISTORICAL_FILINGS_FOUND"
        return "PERIOD_NORMALIZATION_GAP"

    if q_count == 0:
        if member.nse_symbol:
            return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"
        return "BSE_HISTORY_NOT_INGESTED"

    if distinct_fy >= 6 and base_required not in years:
        return "PERIOD_NORMALIZATION_GAP"

    if len(years) >= 1 and q_count >= 4:
        return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"

    return "NO_HISTORICAL_FILINGS_FOUND"


def _classify_annual_gap(
    session: Session,
    member: WatchlistMember,
    *,
    bse: str | None,
    years: list[int],
    q_count: int,
    identities: FinancialDiscoveryIdentitySet | None,
) -> str | None:
    if not bse:
        return "TRUE_NO_ANNUAL_SOURCE"

    if not years:
        if member.security_id:
            aliases = _verified_rename_aliases(session, member.security_id)
            for alias in aliases:
                hist_bse = alias.historical_bse_code
                if hist_bse and _has_annual_for_identifier(session, "BSE_CODE", hist_bse):
                    return "HISTORICAL_ALIAS_NOT_INGESTED"
        if q_count >= 4:
            return "ANNUAL_EXTRACTION_GAP"
        if identities and identities.historical_nse_symbols:
            return "HISTORICAL_ALIAS_NOT_INGESTED"
        if member.nse_symbol:
            return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"
        return "TRUE_NO_ANNUAL_SOURCE"

    if len(years) < 3:
        march_missing = any(
            session.scalar(
                select(func.count())
                .select_from(AnnualFundamentalsSnapshot)
                .where(
                    AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
                    AnnualFundamentalsSnapshot.identifier == bse,
                    AnnualFundamentalsSnapshot.period_end_date == date(fy, 3, 31),
                )
            )
            for fy in years
        )
        if not march_missing and q_count >= 4:
            return "MARCH_YEAR_NOT_INGESTED"
        return "CURRENT_SYMBOL_HISTORY_NOT_INGESTED"

    return None


def classify_member_history(session: Session, member: WatchlistMember) -> HistoryGapReport:
    bse = bse_code(member)
    years = _annual_years(session, bse) if bse else []
    q_count, distinct_fy = _quarterly_stats(session, bse) if bse else (0, 0)
    ph = price_history_summary(session, member)
    span = int(ph.get("span_days") or 0)

    identities = (
        build_financial_discovery_identities(session, member.security_id)
        if member.security_id
        else None
    )
    alias_labels: list[str] = []
    alias_ids: list[str] = []
    if member.security_id:
        for alias in _verified_rename_aliases(session, member.security_id):
            label = alias.alias_name or alias.alias_value
            if label:
                alias_labels.append(label)
        if identities:
            alias_ids = [f"{item.identity_type}:{item.value}" for item in identities.all_identities()]

    latest_fy = max(years) if years else None
    base_required = (latest_fy - 5) if latest_fy is not None else None
    base_available = base_required in years if base_required is not None else False

    cagr_class = _classify_cagr_gap(
        session,
        member,
        bse=bse,
        years=years,
        q_count=q_count,
        distinct_fy=distinct_fy,
        span_days=span,
        latest_fy=latest_fy,
        base_required=base_required,
        base_available=base_available,
        identities=identities,
    )
    annual_class = _classify_annual_gap(
        session,
        member,
        bse=bse,
        years=years,
        q_count=q_count,
        identities=identities,
    )

    return HistoryGapReport(
        member_id=member.member_id,
        display_name=member.display_name,
        security_id=member.security_id,
        bse_code=bse,
        annual_row_count=len(years),
        quarterly_row_count=q_count,
        distinct_fiscal_years=distinct_fy,
        annual_first_fy=min(years) if years else None,
        annual_last_fy=latest_fy,
        price_span_days=span,
        cagr_5y_classification=cagr_class,
        cagr_5y_base_fy_required=base_required,
        cagr_5y_base_fy_available=base_available,
        annual_quality_classification=annual_class,
        verified_historical_aliases=tuple(sorted(set(alias_labels))),
        alias_identifiers=tuple(alias_ids),
    )


def summarize_history_classifications(
    session: Session,
    members: list[WatchlistMember],
) -> dict[str, dict[str, int]]:
    """Count CAGR and annual classifications across members."""
    cagr_counts: dict[str, int] = {}
    annual_counts: dict[str, int] = {}
    for member in members:
        report = classify_member_history(session, member)
        if report.cagr_5y_classification:
            key = report.cagr_5y_classification
            cagr_counts[key] = cagr_counts.get(key, 0) + 1
        if report.annual_quality_classification:
            key = report.annual_quality_classification
            annual_counts[key] = annual_counts.get(key, 0) + 1
    return {"cagr_5y": cagr_counts, "annual_quality": annual_counts}
