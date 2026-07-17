"""Post-exit and sell-assessment tests."""

from decimal import Decimal

from pms_platform.analytics.post_exit import assess_exit_quality


def test_premature_exit_requires_more_than_price_gain_alone() -> None:
    assessment, reason = assess_exit_quality(
        security_return_after_exit=Decimal("30"),
        benchmark_return_after_exit=Decimal("5"),
        maximum_gain_after_exit=Decimal("35"),
        maximum_loss_after_exit=Decimal("-2"),
        data_quality_status="OK",
    )
    assert assessment == "PREMATURE_EXIT"
    assert "benchmark" in reason


def test_insufficient_data_when_post_exit_missing() -> None:
    assessment, _ = assess_exit_quality(
        security_return_after_exit=None,
        benchmark_return_after_exit=None,
        maximum_gain_after_exit=None,
        maximum_loss_after_exit=None,
        data_quality_status="INSUFFICIENT",
    )
    assert assessment == "INSUFFICIENT_DATA"
