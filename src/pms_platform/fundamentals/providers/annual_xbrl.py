"""Annual XBRL fundamentals provider — ROCE, ROE, D/E, etc."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.bse_annual_xbrl import fetch_bse_annual_fundamentals
from pms_platform.market_data.identifiers import IdentifierResolver
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot

_REQUEST_DELAY_SEC = 0.5


@dataclass
class AnnualXbrlImportResult:
    inserted: int
    updated: int
    skipped: int


def upsert_annual_snapshot(
    session: Session,
    *,
    identifier_type: str,
    identifier: str,
    security_id: str | None,
    fiscal_year: int,
    period_end_date: date,
    total_assets: Decimal | None,
    total_equity: Decimal | None,
    total_debt: Decimal | None,
    cash_and_equivalents: Decimal | None,
    finance_costs: Decimal | None,
    current_assets: Decimal | None,
    current_liabilities: Decimal | None,
    roce: Decimal | None,
    roe: Decimal | None,
    roa: Decimal | None,
    debt_to_equity: Decimal | None,
    interest_coverage: Decimal | None,
    current_ratio: Decimal | None,
    sales: Decimal | None = None,
    pat: Decimal | None = None,
    provider: str = "bse_annual_xbrl",
) -> bool:
    """Insert or update an AnnualFundamentalsSnapshot; returns True if new."""
    existing = session.scalar(
        select(AnnualFundamentalsSnapshot).where(
            AnnualFundamentalsSnapshot.identifier_type == identifier_type,
            AnnualFundamentalsSnapshot.identifier == identifier,
            AnnualFundamentalsSnapshot.fiscal_year == fiscal_year,
        )
    )
    fields = dict(
        security_id=security_id,
        period_end_date=period_end_date,
        total_assets=total_assets,
        total_equity=total_equity,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        finance_costs=finance_costs,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        roce=roce,
        roe=roe,
        roa=roa,
        debt_to_equity=debt_to_equity,
        interest_coverage=interest_coverage,
        current_ratio=current_ratio,
        sales=sales,
        pat=pat,
        provider=provider,
        computed_at=datetime.now(timezone.utc),
    )
    if existing is not None:
        for k, v in fields.items():
            if v is None and k not in {"provider", "computed_at", "period_end_date"}:
                continue
            if v is None and k == "security_id":
                continue
            setattr(existing, k, v)
        return False

    session.add(
        AnnualFundamentalsSnapshot(
            identifier_type=identifier_type,
            identifier=identifier,
            fiscal_year=fiscal_year,
            **fields,
        )
    )
    session.flush()
    return True


def refresh_annual_fundamentals(
    session: Session,
    bse_codes: list[str],
    *,
    years_back: int = 3,
    request_delay_sec: float = _REQUEST_DELAY_SEC,
) -> AnnualXbrlImportResult:
    """Fetch annual XBRL filings and upsert AnnualFundamentalsSnapshot rows."""
    resolver = IdentifierResolver(session)
    today = date.today()
    inserted = 0
    updated = 0
    skipped = 0

    for i, bse_code in enumerate(bse_codes):
        if i > 0:
            time.sleep(request_delay_sec)

        try:
            annual_list = fetch_bse_annual_fundamentals(bse_code, years_back=years_back)
        except Exception:
            skipped += 1
            continue

        if not annual_list:
            skipped += 1
            continue

        resolution = resolver.resolve("BSE_CODE", bse_code, today)
        security_id = resolution.security_id if resolution.status == "RESOLVED" else None

        for annual in annual_list:
            is_new = upsert_annual_snapshot(
                session,
                identifier_type="BSE_CODE",
                identifier=bse_code,
                security_id=security_id,
                fiscal_year=annual.fiscal_year,
                period_end_date=annual.period_end_date,
                total_assets=annual.total_assets,
                total_equity=annual.total_equity,
                total_debt=annual.total_debt,
                cash_and_equivalents=annual.cash_and_equivalents,
                finance_costs=annual.finance_costs,
                current_assets=annual.current_assets,
                current_liabilities=annual.current_liabilities,
                roce=annual.roce,
                roe=annual.roe,
                roa=annual.roa,
                debt_to_equity=annual.debt_to_equity,
                interest_coverage=annual.interest_coverage,
                current_ratio=annual.current_ratio,
                sales=annual.sales,
                pat=annual.pat,
            )
            if is_new:
                inserted += 1
            else:
                updated += 1

    session.flush()
    return AnnualXbrlImportResult(inserted=inserted, updated=updated, skipped=skipped)
