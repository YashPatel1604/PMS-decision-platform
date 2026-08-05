"""Tests for official PMS calendar-year portfolio returns."""

from datetime import date
from decimal import Decimal

from pms_platform.analytics.portfolio_calendar_returns import (
    CalendarYearReturn,
    linked_portfolio_return_pct,
)


def test_linked_full_year_product() -> None:
    calendar = {
        2020: CalendarYearReturn(2020, Decimal("1"), None),
        2021: CalendarYearReturn(2021, Decimal("0.5"), None),
    }
    # Full 2020 + full 2021: (1+1)*(1+0.5)-1 = 200%
    result = linked_portfolio_return_pct(
        date(2020, 1, 1), date(2021, 12, 31), calendar=calendar
    )
    assert result == Decimal("200")


def test_missing_year_returns_none() -> None:
    calendar = {2020: CalendarYearReturn(2020, Decimal("0.1"), None)}
    assert (
        linked_portfolio_return_pct(date(2019, 6, 1), date(2020, 6, 1), calendar=calendar)
        is None
    )
