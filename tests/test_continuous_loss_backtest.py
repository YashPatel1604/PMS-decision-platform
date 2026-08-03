"""Continuous-loss diversification backtest tests."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pms_platform.analytics.continuous_loss_backtest import (
    _annualized_return_pct,
    _conclusion,
    _continuous_loss_trigger,
    _equal_capital_values,
)


def _price(trade_date: date, adjusted_close: str):
    return SimpleNamespace(
        trade_date=trade_date,
        adjusted_close=Decimal(adjusted_close),
    )


def test_trigger_occurs_at_365_calendar_days_below_initial_price() -> None:
    path = [
        _price(date(2020, 1, 1), "90"),
        _price(date(2020, 12, 31), "80"),
    ]
    start, trigger = _continuous_loss_trigger(path, Decimal("100"))
    assert start == date(2020, 1, 1)
    assert trigger is not None
    assert trigger.trade_date == date(2020, 12, 31)


def test_recovery_resets_continuous_loss_clock() -> None:
    path = [
        _price(date(2020, 1, 1), "90"),
        _price(date(2020, 12, 30), "100"),
        _price(date(2020, 12, 31), "80"),
        _price(date(2021, 12, 31), "70"),
    ]
    start, trigger = _continuous_loss_trigger(path, Decimal("100"))
    assert start == date(2020, 12, 31)
    assert trigger is not None
    assert trigger.trade_date == date(2021, 12, 31)


def test_outlier_sensitive_conclusion_is_explicit() -> None:
    label, text = _conclusion(
        Decimal("100"),
        Decimal("60"),
        any_flip=False,
    )
    assert label == "POSITIVE_BUT_OUTLIER_SENSITIVE"
    assert "one stock" in text


def test_episode_returns_are_annualized_over_actual_elapsed_time() -> None:
    one_year = _annualized_return_pct(Decimal("21"), 365)
    two_years = _annualized_return_pct(Decimal("21"), 730)
    assert one_year is not None
    assert abs(one_year - Decimal("21")) < Decimal("0.000001")
    assert two_years is not None
    assert Decimal("9.9") < two_years < Decimal("10.1")


def test_equal_capital_summary_gives_every_episode_one_hundred() -> None:
    start, hold_end, diversified_end = _equal_capital_values(
        [
            (Decimal("-52.05"), Decimal("31.85")),
            (Decimal("100"), Decimal("20")),
        ]
    )
    assert start == Decimal("200")
    assert hold_end == Decimal("247.95")
    assert diversified_end == Decimal("251.85")


def test_tie_tolerance_classifies_half_point_as_tie() -> None:
    values = [Decimal("0.5"), Decimal("-0.5"), Decimal("0.6"), Decimal("-0.6")]
    positive = sum(1 for value in values if value > Decimal("0.5"))
    negative = sum(1 for value in values if value < Decimal("-0.5"))
    tie = len(values) - positive - negative
    assert positive == 1
    assert negative == 1
    assert tie == 2
