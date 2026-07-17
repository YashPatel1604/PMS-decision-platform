"""Post-exit and sell-assessment tests."""

from decimal import Decimal

from pms_platform.analytics.exit_assessment import ExitAssessmentInput, assess_exit_quality


def test_premature_exit_requires_more_than_price_gain_alone() -> None:
    result = assess_exit_quality(
        ExitAssessmentInput(
            data_quality_status="OK",
            holding_days=900,
            total_return_pct=Decimal("80"),
            stock_xirr=Decimal("0.15"),
            stock_annualized_return_pct=Decimal("16"),
            smallcap_return_pct=Decimal("60"),
            smallcap_annualized_return_pct=Decimal("12"),
            portfolio_return_pct=Decimal("55"),
            excess_vs_smallcap=Decimal("5"),
            excess_vs_portfolio=Decimal("25"),
            days_underperforming_benchmark=100,
            ownership_trading_days=400,
            max_drawdown_pct=Decimal("12"),
            missed_upside_vs_peak_pct=Decimal("8"),
            security_return_after_exit=Decimal("30"),
            portfolio_return_after_exit=Decimal("5"),
            benchmark_return_after_exit=Decimal("5"),
            maximum_gain_after_exit=Decimal("35"),
            maximum_loss_after_exit=Decimal("-2"),
        )
    )
    assert "PREMATURE_EXIT" in result.flags


def test_insufficient_data_when_post_exit_missing() -> None:
    result = assess_exit_quality(
        ExitAssessmentInput(
            data_quality_status="INSUFFICIENT",
            holding_days=0,
            total_return_pct=None,
            stock_xirr=None,
            stock_annualized_return_pct=None,
            smallcap_return_pct=None,
            smallcap_annualized_return_pct=None,
            portfolio_return_pct=None,
            excess_vs_smallcap=None,
            excess_vs_portfolio=None,
            days_underperforming_benchmark=None,
            ownership_trading_days=None,
            max_drawdown_pct=None,
            missed_upside_vs_peak_pct=None,
            security_return_after_exit=None,
            portfolio_return_after_exit=None,
            benchmark_return_after_exit=None,
            maximum_gain_after_exit=None,
            maximum_loss_after_exit=None,
        )
    )
    assert result.primary == "INSUFFICIENT_DATA"
