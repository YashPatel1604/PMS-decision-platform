"""Missing-reason and provenance metadata for watchlist metrics (v2.0)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.promoter_snapshot import PromoterSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import screen as scr

CRORE = Decimal("10000000")


class MissingReason(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED_SECURITY = "UNRESOLVED_SECURITY"
    NO_EXCHANGE_IDENTIFIER = "NO_EXCHANGE_IDENTIFIER"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    SOURCE_TEMPORARILY_FAILED = "SOURCE_TEMPORARILY_FAILED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    NO_RECENT_FILING = "NO_RECENT_FILING"
    NO_PRICE_HISTORY = "NO_PRICE_HISTORY"
    INVALID_DENOMINATOR = "INVALID_DENOMINATOR"
    NEGATIVE_EARNINGS = "NEGATIVE_EARNINGS"
    STALE_SOURCE = "STALE_SOURCE"
    PARSER_UNSUPPORTED = "PARSER_UNSUPPORTED"
    BACKFILL_PENDING = "BACKFILL_PENDING"
    FIELD_NULL_IN_SOURCE = "FIELD_NULL_IN_SOURCE"
    CACHE_STALE = "CACHE_STALE"
    ANNUAL_BASE_PERIOD_NOT_INGESTED = "ANNUAL_BASE_PERIOD_NOT_INGESTED"
    ANNUAL_REPORT_NOT_FOUND = "ANNUAL_REPORT_NOT_FOUND"
    ANNUAL_XBRL_UNSUPPORTED = "ANNUAL_XBRL_UNSUPPORTED"
    ANNUAL_SOURCE_UNAVAILABLE = "ANNUAL_SOURCE_UNAVAILABLE"
    INVALID_CAGR_BASE = "INVALID_CAGR_BASE"
    TRUE_INSUFFICIENT_LISTING_HISTORY = "TRUE_INSUFFICIENT_LISTING_HISTORY"


class DataQuality(StrEnum):
    PRIMARY_REPORTED = "PRIMARY_REPORTED"
    PRIMARY_DERIVED = "PRIMARY_DERIVED"
    SECONDARY_REPORTED = "SECONDARY_REPORTED"
    FALLBACK = "FALLBACK"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


CAGR_5Y_KEYS = frozenset({"sales_5y_cagr", "pat_5y_cagr"})
CAGR_3Y_KEYS = frozenset({"sales_3y_cagr", "pat_3y_cagr"})
CAGR_KEYS = CAGR_3Y_KEYS | CAGR_5Y_KEYS
PRICE_DERIVED_VAL_KEYS = frozenset(
    {
        "week_52_high",
        "week_52_low",
        "return_1m_pct",
        "return_3m_pct",
        "return_6m_pct",
        "return_1y_pct",
        "return_3y_pct",
        "all_time_high",
    }
)
DERIVED_VAL_KEYS = frozenset({"pe_ratio", "price_to_book", "book_value_per_share", "market_cap_cr", "earnings_yield", "price_to_sales", "peg_ratio"})


@dataclass(frozen=True)
class MemberSnapshotContext:
    bse_code: str | None
    price_rows: int
    quarterly_rows: int
    has_fund: bool
    has_val: bool
    has_annual: bool
    has_prom: bool
    fund_row: FundamentalSnapshot | None
    val_row: ValuationSnapshot | None
    annual_row: AnnualFundamentalsSnapshot | None
    prom_row: PromoterSnapshot | None


def bse_code(member: WatchlistMember) -> str | None:
    code = str(member.bse_code or "").strip()
    if code.endswith(".0"):
        code = code[:-2]
    return code if code.isdigit() else None


def diagnose_missing(
    *,
    member: WatchlistMember,
    metric_key: str,
    value: Decimal | None,
    ctx: MemberSnapshotContext,
    annual_5y: object | None = None,
) -> MissingReason | None:
    if value is not None:
        return None
    if member.resolution_status in {"PENDING", "FAILED", "AMBIGUOUS", "UNSUPPORTED"}:
        return MissingReason.UNRESOLVED_SECURITY
    if member.resolution_status == "EXCHANGE_RESOLVED" and not member.security_id:
        if metric_key in PRICE_DERIVED_VAL_KEYS or metric_key in DERIVED_VAL_KEYS:
            return MissingReason.NO_PRICE_HISTORY
        if not ctx.bse_code and not member.nse_symbol:
            return MissingReason.NO_EXCHANGE_IDENTIFIER
    elif member.resolution_status != "RESOLVED" and not member.security_id:
        return MissingReason.UNRESOLVED_SECURITY
    if not ctx.bse_code and not member.nse_symbol:
        return MissingReason.NO_EXCHANGE_IDENTIFIER
    if metric_key in CAGR_5Y_KEYS:
        from pms_platform.fundamentals.annual_cagr import AnnualCagrResult

        if isinstance(annual_5y, AnnualCagrResult):
            if metric_key == "sales_5y_cagr" and annual_5y.sales_5y_cagr is not None:
                return None
            if metric_key == "pat_5y_cagr" and annual_5y.pat_5y_cagr is not None:
                return None
            if annual_5y.latest_fy is None:
                return MissingReason.ANNUAL_SOURCE_UNAVAILABLE
            base_val = annual_5y.base_sales if metric_key == "sales_5y_cagr" else annual_5y.base_pat
            latest_val = annual_5y.latest_sales if metric_key == "sales_5y_cagr" else annual_5y.latest_pat
            if base_val is not None and base_val <= 0:
                return MissingReason.INVALID_CAGR_BASE
            if base_val is None:
                if ctx.price_rows > 0 and ctx.price_rows < 400:
                    return MissingReason.TRUE_INSUFFICIENT_LISTING_HISTORY
                return MissingReason.ANNUAL_REPORT_NOT_FOUND
            if latest_val is None:
                return MissingReason.ANNUAL_SOURCE_UNAVAILABLE
            return MissingReason.ANNUAL_SOURCE_UNAVAILABLE
        if not ctx.has_annual:
            return MissingReason.ANNUAL_SOURCE_UNAVAILABLE
        return MissingReason.ANNUAL_REPORT_NOT_FOUND
    if metric_key in CAGR_3Y_KEYS:
        if ctx.quarterly_rows < 4:
            return MissingReason.INSUFFICIENT_HISTORY
        if not ctx.has_fund:
            return MissingReason.SOURCE_NOT_AVAILABLE
        return MissingReason.FIELD_NULL_IN_SOURCE
    if metric_key in PRICE_DERIVED_VAL_KEYS:
        if ctx.price_rows == 0:
            return MissingReason.NO_PRICE_HISTORY
        if not ctx.has_val:
            return MissingReason.BACKFILL_PENDING
        return MissingReason.FIELD_NULL_IN_SOURCE
    if metric_key in scr.ANNUAL_FIELDS:
        if not ctx.has_annual:
            return MissingReason.SOURCE_NOT_AVAILABLE
        return MissingReason.FIELD_NULL_IN_SOURCE
    if metric_key in scr.PROMOTER_FIELDS:
        if not ctx.has_prom:
            return MissingReason.SOURCE_NOT_AVAILABLE
        if metric_key == "promoter_holding_change_pp" and ctx.prom_row and ctx.prom_row.promoter_holding_pct:
            return MissingReason.INSUFFICIENT_HISTORY
        return MissingReason.FIELD_NULL_IN_SOURCE
    if metric_key in scr.SNAPSHOT_FIELDS:
        if not ctx.has_fund:
            return MissingReason.SOURCE_NOT_AVAILABLE
        if ctx.fund_row is None:
            return MissingReason.NO_RECENT_FILING
        return MissingReason.FIELD_NULL_IN_SOURCE
    if metric_key in scr.VALUATION_FIELDS:
        if not ctx.has_val:
            return MissingReason.SOURCE_NOT_AVAILABLE
        if metric_key == "pe_ratio" and ctx.val_row and ctx.val_row.pe_ratio is None:
            pat = ctx.fund_row.pat if ctx.fund_row else None
            if pat is not None and pat <= 0:
                return MissingReason.NEGATIVE_EARNINGS
            return MissingReason.FIELD_NULL_IN_SOURCE
        if metric_key in {"peg_ratio", "price_to_sales", "industry_pe", "dividend_yield", "price_to_book", "book_value_per_share"}:
            return MissingReason.FIELD_NULL_IN_SOURCE
        return MissingReason.FIELD_NULL_IN_SOURCE
    return MissingReason.SOURCE_NOT_AVAILABLE


def _provider_quality(provider: str | None) -> DataQuality:
    if not provider:
        return DataQuality.UNAVAILABLE
    p = provider.casefold()
    if p in {"nse_xbrl", "xbrl", "bse_annual_xbrl"}:
        return DataQuality.PRIMARY_REPORTED
    if p in {"derived_v2", "computed", "price_history"}:
        return DataQuality.PRIMARY_DERIVED
    if p == "screener":
        return DataQuality.SECONDARY_REPORTED
    if p in {"bse_quote", "yahoo", "yahoo_finance"}:
        return DataQuality.FALLBACK
    return DataQuality.PRIMARY_REPORTED


def provenance_for_metric(
    metric_key: str,
    value: Decimal | None,
    ctx: MemberSnapshotContext,
    *,
    computation_version: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if metric_key in scr.SNAPSHOT_FIELDS and ctx.fund_row:
        return {
            "provider": ctx.fund_row.provider,
            "source": "computed" if metric_key.endswith("_pct") or metric_key.endswith("_cagr") or metric_key.endswith("_pp") else "reported",
            "period_end": ctx.fund_row.period_end_date.isoformat(),
            "fiscal_year": ctx.fund_row.fiscal_year,
            "fiscal_quarter": ctx.fund_row.fiscal_quarter,
            "computation_version": computation_version,
            "quality": _provider_quality(ctx.fund_row.provider).value,
        }
    if metric_key in scr.ANNUAL_FIELDS and ctx.annual_row:
        return {
            "provider": ctx.annual_row.provider,
            "source": "computed" if metric_key in scr.ANNUAL_FIELDS else "reported",
            "fiscal_year": ctx.annual_row.fiscal_year,
            "period_end": ctx.annual_row.period_end_date.isoformat(),
            "computation_version": computation_version,
            "quality": _provider_quality(ctx.annual_row.provider).value,
        }
    if metric_key in scr.PROMOTER_FIELDS and ctx.prom_row:
        return {
            "provider": ctx.prom_row.provider,
            "source": "reported",
            "quarter_end": ctx.prom_row.quarter_end_date.isoformat() if ctx.prom_row.quarter_end_date else None,
            "quality": _provider_quality(ctx.prom_row.provider).value,
        }
    if metric_key in scr.VALUATION_FIELDS and ctx.val_row:
        source = "derived" if metric_key in DERIVED_VAL_KEYS and ctx.val_row.provider == "derived_v2" else "reported"
        return {
            "provider": ctx.val_row.provider,
            "source": source,
            "as_of_date": ctx.val_row.as_of_date.isoformat(),
            "computation_version": computation_version,
            "quality": _provider_quality(ctx.val_row.provider).value,
        }
    return {"source": "unknown", "quality": DataQuality.UNAVAILABLE.value}


def build_member_diagnostics(
    session,
    member: WatchlistMember,
    metrics: dict[str, Decimal | None],
    ctx: MemberSnapshotContext,
    *,
    computation_version: str,
    metric_keys: tuple[str, ...],
) -> dict[str, Any]:
    from pms_platform.fundamentals.annual_cagr import compute_annual_5y_cagr
    from pms_platform.watchlists.financial_discovery import build_financial_discovery_identities

    annual_5y = None
    if ctx.bse_code and any(k in metric_keys for k in CAGR_5Y_KEYS):
        extra_bse: tuple[str, ...] = ()
        if member.security_id:
            ids = build_financial_discovery_identities(session, member.security_id)
            if ids:
                extra_bse = ids.historical_bse_codes
        annual_5y = compute_annual_5y_cagr(session, ctx.bse_code, extra_bse_codes=extra_bse)

    missing_reasons: dict[str, str] = {}
    provenance: dict[str, Any] = {}
    quality: dict[str, str] = {}

    for key in metric_keys:
        val = metrics.get(key)
        reason = diagnose_missing(
            member=member,
            metric_key=key,
            value=val,
            ctx=ctx,
            annual_5y=annual_5y,
        )
        if reason is not None:
            missing_reasons[key] = reason.value
            quality[key] = DataQuality.UNAVAILABLE.value
        else:
            prov = provenance_for_metric(key, val, ctx, computation_version=computation_version)
            if prov:
                provenance[key] = prov
                quality[key] = prov.get("quality", DataQuality.PRIMARY_REPORTED.value)

    return {
        "computation_version": computation_version,
        "missing_reasons": missing_reasons,
        "provenance": provenance,
        "quality": quality,
        "freshness": {
            "price_rows": ctx.price_rows,
            "quarterly_rows": ctx.quarterly_rows,
            "fundamentals_as_of": (
                ctx.fund_row.period_end_date.isoformat() if ctx.fund_row and ctx.fund_row.period_end_date else None
            ),
            "annual_as_of": (
                ctx.annual_row.period_end_date.isoformat() if ctx.annual_row and ctx.annual_row.period_end_date else None
            ),
            "valuation_as_of": ctx.val_row.as_of_date.isoformat() if ctx.val_row else None,
            "shareholding_as_of": (
                ctx.prom_row.quarter_end_date.isoformat() if ctx.prom_row and ctx.prom_row.quarter_end_date else None
            ),
        },
    }
