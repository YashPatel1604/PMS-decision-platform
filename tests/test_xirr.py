"""XIRR calculation tests."""

from datetime import date
from decimal import Decimal

from pms_platform.analytics.xirr import compute_xirr


def test_xirr_single_buy_and_full_exit() -> None:
    flows = [
        (date(2020, 1, 1), Decimal("-1000")),
        (date(2021, 1, 1), Decimal("2000")),
    ]
    result = compute_xirr(flows)
    assert result is not None
    assert abs(result - Decimal("0.99621589")) < Decimal("0.0001")


def test_xirr_multiple_buys_and_partial_sell() -> None:
    flows = [
        (date(2020, 1, 1), Decimal("-1000")),
        (date(2020, 6, 1), Decimal("-500")),
        (date(2021, 1, 1), Decimal("1800")),
    ]
    result = compute_xirr(flows)
    assert result is not None
    assert result > Decimal("0")


def test_xirr_returns_none_without_sign_mix() -> None:
    assert compute_xirr([(date(2020, 1, 1), Decimal("100"))]) is None
    assert (
        compute_xirr(
            [
                (date(2020, 1, 1), Decimal("100")),
                (date(2021, 1, 1), Decimal("200")),
            ]
        )
        is None
    )
