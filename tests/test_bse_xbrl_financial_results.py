"""Tests for BSE financial-results XBRL parsing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pms_platform.market_data.bse_financial_results import BseQuarterlyResult
from pms_platform.market_data.bse_xbrl_financial_results import (
    merge_quarterly_results,
    parse_xbrl_quarterly_result,
)

FIXTURE = Path("tests/fixtures/market_data/bse/financial_results_xbrl.xml")


def test_parse_xbrl_quarterly_result() -> None:
    quarter = parse_xbrl_quarterly_result(FIXTURE.read_bytes())

    assert quarter is not None
    assert quarter.period_end_date == date(2024, 12, 31)
    assert quarter.fiscal_quarter == "Q3"
    assert quarter.sales == Decimal("96.85")
    assert quarter.pat == Decimal("26.03")
    assert quarter.opm == Decimal("17.70")
    assert quarter.npm == Decimal("26.87")


def test_merge_quarterly_results_prefers_tabresults() -> None:
    tab = (
        BseQuarterlyResult(
            period_label="Dec-24",
            period_end_date=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_quarter="Q3",
            sales=Decimal("96.00"),
            pat=Decimal("25.00"),
            opm=Decimal("18.00"),
            npm=Decimal("26.00"),
        ),
    )
    xbrl = (
        BseQuarterlyResult(
            period_label="Dec-24",
            period_end_date=date(2024, 12, 31),
            fiscal_year=2024,
            fiscal_quarter="Q3",
            sales=Decimal("96.85"),
            pat=Decimal("26.03"),
            opm=Decimal("18.54"),
            npm=Decimal("26.87"),
        ),
        BseQuarterlyResult(
            period_label="Sep-24",
            period_end_date=date(2024, 9, 30),
            fiscal_year=2024,
            fiscal_quarter="Q2",
            sales=Decimal("80.00"),
            pat=Decimal("10.00"),
            opm=Decimal("12.00"),
            npm=Decimal("12.50"),
        ),
    )

    merged = merge_quarterly_results(tab, xbrl)

    assert len(merged) == 2
    dec = merged[1]
    assert dec.sales == Decimal("96.00")
    assert merged[0].period_end_date == date(2024, 9, 30)
