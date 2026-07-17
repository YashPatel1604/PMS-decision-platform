"""Exit assessment tests."""

from decimal import Decimal

from pms_platform.analytics.exit_assessment import ExitAssessmentInput, assess_exit_quality


def _base_input(**overrides) -> ExitAssessmentInput:
    data = {
        "data_quality_status": "OK",
        "holding_days": 3650,
        "total_return_pct": Decimal("200"),
        "stock_xirr": Decimal("0.10"),
        "stock_annualized_return_pct": Decimal("11.6"),
        "smallcap_return_pct": Decimal("280"),
        "smallcap_annualized_return_pct": Decimal("14"),
        "portfolio_return_pct": Decimal("220"),
        "excess_vs_smallcap": Decimal("-5"),
        "excess_vs_portfolio": Decimal("-20"),
        "days_underperforming_benchmark": 1200,
        "ownership_trading_days": 1800,
        "max_drawdown_pct": Decimal("40"),
        "missed_upside_vs_peak_pct": Decimal("30"),
        "security_return_after_exit": Decimal("5"),
        "portfolio_return_after_exit": Decimal("8"),
        "benchmark_return_after_exit": Decimal("8"),
        "maximum_gain_after_exit": Decimal("10"),
        "maximum_loss_after_exit": Decimal("-3"),
    }
    data.update(overrides)
    return ExitAssessmentInput(**data)


def test_late_exit_and_rotation_flags_for_long_mediocre_hold() -> None:
    result = assess_exit_quality(_base_input())
    assert "LATE_EXIT" in result.flags
    assert "CAPITAL_ROTATION_MISSED" in result.flags
    assert "GAVE_BACK_GAINS" in result.flags


def test_premature_exit_when_post_exit_beats_benchmark_and_portfolio() -> None:
    result = assess_exit_quality(
        _base_input(
            holding_days=800,
            total_return_pct=Decimal("120"),
            stock_xirr=Decimal("0.18"),
            stock_annualized_return_pct=Decimal("18"),
            excess_vs_smallcap=Decimal("10"),
            missed_upside_vs_peak_pct=Decimal("5"),
            max_drawdown_pct=Decimal("10"),
            security_return_after_exit=Decimal("30"),
            portfolio_return_after_exit=Decimal("5"),
            benchmark_return_after_exit=Decimal("5"),
        )
    )
    assert "PREMATURE_EXIT" in result.flags


def test_index_outperformed_hold_for_saregama_style_case() -> None:
    result = assess_exit_quality(
        _base_input(
            holding_days=900,
            total_return_pct=Decimal("80"),
            stock_xirr=Decimal("0.12"),
            stock_annualized_return_pct=Decimal("14"),
            excess_vs_smallcap=Decimal("5"),
            missed_upside_vs_peak_pct=Decimal("5"),
            max_drawdown_pct=Decimal("10"),
            security_return_after_exit=Decimal("28"),
            portfolio_return_after_exit=Decimal("60"),
            benchmark_return_after_exit=Decimal("98"),
        )
    )
    assert "LEFT_STOCK_UPSIDE" in result.flags
    assert "INDEX_OUTPERFORMED_HOLD" in result.flags
    assert "PORTFOLIO_OUTPERFORMED_HOLD" in result.flags
    assert "After exit:" in result.reason


def test_insufficient_data() -> None:
    result = assess_exit_quality(_base_input(data_quality_status="INSUFFICIENT"))
    assert result.primary == "INSUFFICIENT_DATA"
