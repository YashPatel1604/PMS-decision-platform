"""Tests for screener metric expansion modules."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pms_platform.fundamentals.compute import compute_cagr, compute_snapshots_for_identifier
from pms_platform.market_data.bse_stock_quote import _to_dec
from pms_platform.market_data.price_returns import compute_price_returns


class _FakeQuarterlyRow:
    def __init__(
        self,
        *,
        identifier_type: str = "BSE_CODE",
        identifier: str = "500001",
        security_id: str | None = None,
        fiscal_year: int,
        fiscal_quarter: str,
        period_end_date: date,
        sales: Decimal | None = None,
        pat: Decimal | None = None,
        opm: Decimal | None = None,
        npm: Decimal | None = None,
        provider: str = "xbrl",
        retrieved_at=None,
    ):
        self.identifier_type = identifier_type
        self.identifier = identifier
        self.security_id = security_id
        self.fiscal_year = fiscal_year
        self.fiscal_quarter = fiscal_quarter
        self.period_end_date = period_end_date
        self.sales = sales
        self.pat = pat
        self.opm = opm
        self.npm = npm
        self.provider = provider
        self.retrieved_at = retrieved_at


class _FakeDailyPrice:
    def __init__(self, trade_date: date, close: Decimal, adjusted_close: Decimal | None = None):
        self.identifier_type = "BSE_CODE"
        self.identifier = "500001"
        self.trade_date = trade_date
        self.close = close
        self.adjusted_close = adjusted_close or close


def test_compute_cagr_positive():
    result = compute_cagr(Decimal("120"), Decimal("80"), 3)
    assert result is not None
    assert result > Decimal("0")


def test_compute_cagr_none_when_prior_zero():
    assert compute_cagr(Decimal("120"), Decimal("0"), 3) is None


def test_compute_cagr_none_when_missing():
    assert compute_cagr(None, Decimal("80"), 3) is None


def test_compute_snapshots_includes_cagr():
    rows = [
        _FakeQuarterlyRow(
            fiscal_year=2022, fiscal_quarter="Q1",
            period_end_date=date(2021, 6, 30), sales=Decimal("100"), pat=Decimal("10"),
        ),
        _FakeQuarterlyRow(
            fiscal_year=2023, fiscal_quarter="Q1",
            period_end_date=date(2022, 6, 30), sales=Decimal("110"), pat=Decimal("11"),
        ),
        _FakeQuarterlyRow(
            fiscal_year=2024, fiscal_quarter="Q1",
            period_end_date=date(2023, 6, 30), sales=Decimal("121"), pat=Decimal("12"),
        ),
        _FakeQuarterlyRow(
            fiscal_year=2025, fiscal_quarter="Q1",
            period_end_date=date(2024, 6, 30), sales=Decimal("133"), pat=Decimal("13"),
        ),
    ]
    snapshots = compute_snapshots_for_identifier(rows)
    latest = snapshots[-1]
    assert latest.sales_3y_cagr is not None
    assert latest.pat_3y_cagr is not None


def test_to_dec_strips_commas():
    assert _to_dec("4,019.46") == Decimal("4019.46")
    assert _to_dec("-") is None


def test_compute_price_returns():
    ref = date(2025, 8, 1)
    prices = []
    for i in range(400):
        d = ref - timedelta(days=i)
        prices.append(_FakeDailyPrice(d, Decimal("100") + Decimal(str(i % 10))))
    result = compute_price_returns(prices, reference_date=ref)
    assert result is not None
    assert result.all_time_high is not None
    assert result.return_1y_pct is not None
    assert result.week_52_high is not None
    assert result.week_52_low is not None
