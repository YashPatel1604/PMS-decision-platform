"""Computed growth and margin metrics from quarterly fundamentals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from pms_platform.fundamentals.catalog import COMPUTATION_VERSION
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ComputedSnapshot:
    """Computed metrics for one quarter before persistence."""

    identifier_type: str
    identifier: str
    security_id: str | None
    fiscal_year: int
    fiscal_quarter: str
    period_end_date: object
    sales: Decimal | None
    pat: Decimal | None
    opm: Decimal | None
    npm: Decimal | None
    sales_yoy_pct: Decimal | None
    sales_qoq_pct: Decimal | None
    pat_yoy_pct: Decimal | None
    opm_delta_pp: Decimal | None
    npm_delta_pp: Decimal | None
    sales_3y_cagr: Decimal | None = None
    sales_5y_cagr: Decimal | None = None
    pat_3y_cagr: Decimal | None = None
    pat_5y_cagr: Decimal | None = None
    provider: str = "unknown"
    retrieved_at: datetime | None = None


def pct_change(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """Null-safe percent change; returns None when prior is zero or missing."""
    if current is None or prior is None or prior == 0:
        return None
    return ((current - prior) / abs(prior)) * HUNDRED


def pp_change(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """Null-safe percentage-point change for margin fields stored as percent."""
    if current is None or prior is None:
        return None
    return current - prior


def compute_cagr(
    current: Decimal | None,
    prior: Decimal | None,
    years: int,
) -> Decimal | None:
    """Compute CAGR from current and prior values over `years` years.

    Returns percentage (e.g. 15.23 for 15.23%). Returns None if prior is zero,
    negative, or missing.
    """
    if current is None or prior is None or prior <= 0 or years <= 0:
        return None
    try:
        ratio = float(current / prior)
        if ratio <= 0:
            return None
        cagr_decimal = ratio ** (1.0 / years) - 1.0
        return (Decimal(str(round(cagr_decimal * 100, 4)))).quantize(Decimal("0.0001"))
    except (ZeroDivisionError, OverflowError):
        return None


def _quarter_key(row: CompanyFundamentalsQuarterly) -> tuple[int, str]:
    return row.fiscal_year, row.fiscal_quarter


_PROVIDER_RANK = {
    "nse_xbrl": 0,
    "xbrl": 1,
    "bse_xbrl": 1,
    "bse_tabresults": 2,
    "manual": 3,
    "screener": 4,
    "yahoo": 5,
    "unknown": 9,
}


def _provider_rank(provider: str | None) -> int:
    return _PROVIDER_RANK.get((provider or "unknown").lower(), 9)


def dedupe_quarterly_rows(
    rows: list[CompanyFundamentalsQuarterly],
) -> list[CompanyFundamentalsQuarterly]:
    """Keep one quarterly row per period_end_date (best provider wins)."""
    by_period: dict[object, CompanyFundamentalsQuarterly] = {}
    for row in rows:
        key = row.period_end_date
        existing = by_period.get(key)
        if existing is None:
            by_period[key] = row
            continue
        row_rank = _provider_rank(row.provider)
        existing_rank = _provider_rank(existing.provider)
        if row_rank < existing_rank:
            by_period[key] = row
            continue
        if row_rank > existing_rank:
            continue
        row_ts = row.retrieved_at or datetime.min.replace(tzinfo=timezone.utc)
        existing_ts = existing.retrieved_at or datetime.min.replace(tzinfo=timezone.utc)
        if row_ts >= existing_ts:
            by_period[key] = row
    return sorted(by_period.values(), key=lambda row: row.period_end_date)


def _index_rows(
    rows: list[CompanyFundamentalsQuarterly],
) -> dict[tuple[int, str], CompanyFundamentalsQuarterly]:
    return {_quarter_key(row): row for row in rows}


def compute_snapshots_for_identifier(
    rows: list[CompanyFundamentalsQuarterly],
) -> list[ComputedSnapshot]:
    """Compute YoY/QoQ metrics for all quarters of one identifier."""
    if not rows:
        return []

    sorted_rows = dedupe_quarterly_rows(rows)
    by_key = _index_rows(sorted_rows)
    snapshots: list[ComputedSnapshot] = []

    for index, row in enumerate(sorted_rows):
        prior_q = sorted_rows[index - 1] if index > 0 else None
        prior_y = by_key.get((row.fiscal_year - 1, row.fiscal_quarter))
        prior_3y = by_key.get((row.fiscal_year - 3, row.fiscal_quarter))
        prior_5y = by_key.get((row.fiscal_year - 5, row.fiscal_quarter))

        snapshots.append(
            ComputedSnapshot(
                identifier_type=row.identifier_type,
                identifier=row.identifier,
                security_id=row.security_id,
                fiscal_year=row.fiscal_year,
                fiscal_quarter=row.fiscal_quarter,
                period_end_date=row.period_end_date,
                sales=row.sales,
                pat=row.pat,
                opm=row.opm,
                npm=row.npm,
                sales_yoy_pct=pct_change(row.sales, prior_y.sales if prior_y else None),
                sales_qoq_pct=pct_change(row.sales, prior_q.sales if prior_q else None),
                pat_yoy_pct=pct_change(row.pat, prior_y.pat if prior_y else None),
                opm_delta_pp=pp_change(row.opm, prior_y.opm if prior_y else None),
                npm_delta_pp=pp_change(row.npm, prior_y.npm if prior_y else None),
                sales_3y_cagr=compute_cagr(row.sales, prior_3y.sales if prior_3y else None, 3),
                sales_5y_cagr=None,  # FY annual pipeline — see fundamentals.annual_cagr
                pat_3y_cagr=compute_cagr(row.pat, prior_3y.pat if prior_3y else None, 3),
                pat_5y_cagr=None,
                provider=row.provider,
                retrieved_at=row.retrieved_at,
            )
        )

    return snapshots


def _snapshot_identity(
    computed: ComputedSnapshot,
    *,
    computation_version: str,
) -> tuple[str, str, object, str]:
    return (
        computed.identifier_type,
        computed.identifier,
        computed.period_end_date,
        computation_version,
    )


def _apply_snapshot_fields(
    row: FundamentalSnapshot,
    computed: ComputedSnapshot,
    *,
    computation_version: str,
) -> None:
    row.security_id = computed.security_id
    row.fiscal_year = computed.fiscal_year
    row.fiscal_quarter = computed.fiscal_quarter
    row.sales = computed.sales
    row.pat = computed.pat
    row.opm = computed.opm
    row.npm = computed.npm
    row.sales_yoy_pct = computed.sales_yoy_pct
    row.sales_qoq_pct = computed.sales_qoq_pct
    row.pat_yoy_pct = computed.pat_yoy_pct
    row.opm_delta_pp = computed.opm_delta_pp
    row.npm_delta_pp = computed.npm_delta_pp
    row.sales_3y_cagr = computed.sales_3y_cagr
    row.sales_5y_cagr = computed.sales_5y_cagr
    row.pat_3y_cagr = computed.pat_3y_cagr
    row.pat_5y_cagr = computed.pat_5y_cagr
    row.provider = computed.provider
    row.retrieved_at = computed.retrieved_at
    row.computation_version = computation_version
    row.computed_at = datetime.now(timezone.utc)


def upsert_snapshot(
    session,
    computed: ComputedSnapshot,
    *,
    computation_version: str = COMPUTATION_VERSION,
    pending: dict[tuple[str, str, object, str], FundamentalSnapshot] | None = None,
) -> FundamentalSnapshot:
    """Insert or update a computed snapshot row (safe within one flush batch)."""
    from sqlalchemy import select

    key = _snapshot_identity(computed, computation_version=computation_version)
    if pending is not None:
        existing = pending.get(key)
        if existing is not None:
            _apply_snapshot_fields(existing, computed, computation_version=computation_version)
            return existing

    existing = session.scalar(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier_type == key[0],
            FundamentalSnapshot.identifier == key[1],
            FundamentalSnapshot.period_end_date == key[2],
            FundamentalSnapshot.computation_version == key[3],
        )
    )
    if existing is not None:
        _apply_snapshot_fields(existing, computed, computation_version=computation_version)
        if pending is not None:
            pending[key] = existing
        return existing

    row = FundamentalSnapshot(
        identifier_type=computed.identifier_type,
        identifier=computed.identifier,
        security_id=computed.security_id,
        fiscal_year=computed.fiscal_year,
        fiscal_quarter=computed.fiscal_quarter,
        period_end_date=computed.period_end_date,
        sales=computed.sales,
        pat=computed.pat,
        opm=computed.opm,
        npm=computed.npm,
        sales_yoy_pct=computed.sales_yoy_pct,
        sales_qoq_pct=computed.sales_qoq_pct,
        pat_yoy_pct=computed.pat_yoy_pct,
        opm_delta_pp=computed.opm_delta_pp,
        npm_delta_pp=computed.npm_delta_pp,
        sales_3y_cagr=computed.sales_3y_cagr,
        sales_5y_cagr=computed.sales_5y_cagr,
        pat_3y_cagr=computed.pat_3y_cagr,
        pat_5y_cagr=computed.pat_5y_cagr,
        provider=computed.provider,
        retrieved_at=computed.retrieved_at,
        computation_version=computation_version,
    )
    session.add(row)
    if pending is not None:
        pending[key] = row
    return row
