"""Post-exit horizon and assessment tests."""

from datetime import date
from decimal import Decimal

from pms_platform.analytics.exit_assessment import (
    ExitAssessmentInput,
    assess_exit_quality,
)
from pms_platform.analytics.post_exit import _add_years


def _input(**overrides) -> ExitAssessmentInput:
    values = {
        "ownership_data_status": "OK",
        "one_year_data_status": "OK",
        "holding_days": 900,
        "stock_annualized_return_pct": Decimal("16"),
        "smallcap_annualized_return_pct": Decimal("12"),
        "days_underperforming_benchmark": 100,
        "ownership_trading_days": 400,
        "max_unrealized_gain_pct": Decimal("20"),
        "missed_upside_vs_peak_pct": Decimal("8"),
        "peak_to_exit_days": 20,
        "continuous_underwater_days": 0,
        "one_year_stock_return_pct": Decimal("30"),
        "one_year_smallcap_return_pct": Decimal("20"),
    }
    values.update(overrides)
    return ExitAssessmentInput(**values)


def test_missed_compounding_requires_benchmark_excess() -> None:
    result = assess_exit_quality(
        _input(
            one_year_stock_return_pct=Decimal("30"),
            one_year_smallcap_return_pct=Decimal("28"),
        )
    )
    assert result.primary == "NO_STRONG_SIGNAL"
    assert result.post_exit_flags == ("NO_STRONG_POST_EXIT_SIGNAL",)


def test_missing_one_year_data_is_insufficient() -> None:
    result = assess_exit_quality(
        _input(
            one_year_data_status="INSUFFICIENT",
            one_year_stock_return_pct=None,
            one_year_smallcap_return_pct=None,
        )
    )
    assert result.primary == "INSUFFICIENT_DATA"


def test_standard_horizon_dates_use_calendar_anniversaries() -> None:
    exit_date = date(2020, 7, 21)
    assert _add_years(exit_date, 1) == date(2021, 7, 21)
    assert _add_years(exit_date, 3) == date(2023, 7, 21)
    assert _add_years(exit_date, 5) == date(2025, 7, 21)


def test_leap_day_horizon_falls_back_to_february_28() -> None:
    assert _add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)


def test_recent_exit_maps_to_too_recent_verdict() -> None:
    result = assess_exit_quality(
        _input(
            one_year_data_status="TOO_RECENT",
            one_year_stock_return_pct=None,
            one_year_smallcap_return_pct=None,
        )
    )
    assert result.primary == "TOO_RECENT_TO_JUDGE"
