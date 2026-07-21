"""Dimensional exit-assessment tests."""

from decimal import Decimal

from pms_platform.analytics.exit_assessment import (
    ExitAssessmentInput,
    assess_exit_quality,
)


def _input(**overrides) -> ExitAssessmentInput:
    values = {
        "ownership_data_status": "OK",
        "one_year_data_status": "OK",
        "holding_days": 900,
        "stock_annualized_return_pct": Decimal("15"),
        "smallcap_annualized_return_pct": Decimal("14"),
        "days_underperforming_benchmark": 200,
        "ownership_trading_days": 600,
        "max_unrealized_gain_pct": Decimal("20"),
        "missed_upside_vs_peak_pct": Decimal("10"),
        "peak_to_exit_days": 50,
        "continuous_underwater_days": 20,
        "one_year_stock_return_pct": Decimal("5"),
        "one_year_smallcap_return_pct": Decimal("7"),
    }
    values.update(overrides)
    return ExitAssessmentInput(**values)


def test_well_timed_exit_when_downside_avoided_without_ownership_failure() -> None:
    result = assess_exit_quality(
        _input(one_year_stock_return_pct=Decimal("-12"))
    )
    assert result.primary == "WELL_TIMED_EXIT"
    assert result.post_exit_flags == ("DOWNSIDE_AVOIDED",)
    assert result.ownership_flags == ()


def test_too_early_when_stock_compounds_and_beats_smallcap() -> None:
    result = assess_exit_quality(
        _input(
            one_year_stock_return_pct=Decimal("25"),
            one_year_smallcap_return_pct=Decimal("15"),
        )
    )
    assert result.primary == "EXIT_TOO_EARLY"
    assert result.post_exit_flags == ("MISSED_COMPOUNDING",)


def test_late_exit_from_selective_ownership_signals() -> None:
    result = assess_exit_quality(
        _input(
            holding_days=1900,
            stock_annualized_return_pct=Decimal("7"),
            smallcap_annualized_return_pct=Decimal("15"),
            days_underperforming_benchmark=800,
            ownership_trading_days=1000,
            continuous_underwater_days=400,
            one_year_stock_return_pct=Decimal("0"),
            one_year_smallcap_return_pct=Decimal("15"),
        )
    )
    assert result.primary == "EXIT_TOO_LATE"
    assert "SUSTAINED_BENCHMARK_LAG" in result.ownership_flags
    assert "LONG_UNDERWATER" in result.ownership_flags
    assert "CAPITAL_ROTATION_MISSED" in result.ownership_flags
    assert result.post_exit_flags == ("BENCHMARK_ROTATION_JUSTIFIED",)


def test_conflicting_pre_and_post_evidence_is_mixed() -> None:
    result = assess_exit_quality(
        _input(
            holding_days=1200,
            stock_annualized_return_pct=Decimal("8"),
            smallcap_annualized_return_pct=Decimal("15"),
            days_underperforming_benchmark=700,
            ownership_trading_days=900,
            one_year_stock_return_pct=Decimal("30"),
            one_year_smallcap_return_pct=Decimal("20"),
        )
    )
    assert result.primary == "MIXED_EVIDENCE"
    assert "SUSTAINED_BENCHMARK_LAG" in result.ownership_flags
    assert result.post_exit_flags == ("MISSED_COMPOUNDING",)


def test_peak_giveback_requires_all_conditions() -> None:
    qualifying = assess_exit_quality(
        _input(
            max_unrealized_gain_pct=Decimal("80"),
            missed_upside_vs_peak_pct=Decimal("30"),
            peak_to_exit_days=120,
        )
    )
    assert "PEAK_GIVEBACK" in qualifying.ownership_flags

    short_decline = assess_exit_quality(
        _input(
            max_unrealized_gain_pct=Decimal("80"),
            missed_upside_vs_peak_pct=Decimal("30"),
            peak_to_exit_days=89,
        )
    )
    assert "PEAK_GIVEBACK" not in short_decline.ownership_flags


def test_recent_exit_is_not_judged_without_severe_ownership_problem() -> None:
    result = assess_exit_quality(_input(one_year_data_status="TOO_RECENT"))
    assert result.primary == "TOO_RECENT_TO_JUDGE"
    assert result.confidence == "LOW"


def test_insufficient_ownership_data() -> None:
    result = assess_exit_quality(_input(ownership_data_status="INSUFFICIENT"))
    assert result.primary == "INSUFFICIENT_DATA"


def test_threshold_boundaries_are_inclusive() -> None:
    result = assess_exit_quality(
        _input(
            one_year_stock_return_pct=Decimal("15"),
            one_year_smallcap_return_pct=Decimal("10"),
        )
    )
    assert result.post_exit_flags == ("MISSED_COMPOUNDING",)
