"""Tests for BSE Integrated Finance iXBRL HTML parsing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.market_data.bse_integrated_finance import parse_integrated_finance_html

FIXTURE = Path("tests/fixtures/market_data/bse/integrated_finance_standalone.html")


def test_parse_integrated_finance_html_crores() -> None:
    quarter = parse_integrated_finance_html(FIXTURE.read_text())

    assert quarter is not None
    assert quarter.period_end_date == date(2025, 6, 30)
    assert quarter.fiscal_quarter == "Q1"
    assert quarter.sales == Decimal("106.02")
    assert quarter.pat == Decimal("28.50")
    assert quarter.opm == Decimal("25.00")
    assert quarter.npm == Decimal("26.88")


def test_parse_integrated_finance_html_lakhs() -> None:
    html = FIXTURE.read_text().replace("Crores", "Lakhs").replace("106.02", "10602.00")
    quarter = parse_integrated_finance_html(html)

    assert quarter is not None
    assert quarter.sales == Decimal("106.02")
