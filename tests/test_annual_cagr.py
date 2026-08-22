"""Tests for FY-based 5Y CAGR from annual endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pms_platform.fundamentals.annual_cagr import compute_annual_5y_cagr
from pms_platform.fundamentals.providers.annual_xbrl import upsert_annual_snapshot
from pms_platform.models import ImportBatch, Security


def test_annual_5y_cagr_from_fy_endpoints(session, import_batch: ImportBatch) -> None:
    sec = Security(
        security_id="SEC500",
        portfolio_name="Test",
        bse_code="500500",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(sec)
    session.flush()

    for fy, sales in ((2021, Decimal("100")), (2026, Decimal("200"))):
        upsert_annual_snapshot(
            session,
            identifier_type="BSE_CODE",
            identifier="500500",
            security_id=sec.security_id,
            fiscal_year=fy,
            period_end_date=date(fy, 3, 31),
            sales=sales,
            pat=sales * Decimal("0.1"),
            total_assets=Decimal("1000"),
            total_equity=Decimal("500"),
            total_debt=None,
            cash_and_equivalents=None,
            finance_costs=None,
            current_assets=None,
            current_liabilities=None,
            roce=None,
            roe=None,
            roa=None,
            debt_to_equity=None,
            interest_coverage=None,
            current_ratio=None,
            provider="test",
        )
    session.flush()

    result = compute_annual_5y_cagr(session, "500500")
    assert result.latest_period_end == date(2026, 3, 31)
    assert result.base_period_end == date(2021, 3, 31)
    assert result.sales_5y_cagr == Decimal("14.8698")
    assert result.pat_5y_cagr == Decimal("14.8698")
