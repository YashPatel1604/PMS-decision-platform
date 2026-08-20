"""Portfolio Change-note harvest parser checks."""

from datetime import date
from decimal import Decimal

from pms_platform.ingestion.portfolio_change_harvest import parse_change_note


def test_parse_add_with_amount() -> None:
    assert parse_change_note("Add 550@683.63 = 375997") == (
        "Buy",
        550,
        Decimal("683.63"),
        Decimal("375997"),
    )


def test_parse_buy() -> None:
    assert parse_change_note("Buy 532@525.87 = 279763") == (
        "Buy",
        532,
        Decimal("525.87"),
        Decimal("279763"),
    )


def test_parse_sell_without_amount() -> None:
    event, qty, price, amount = parse_change_note("Sell 1840@169.66")  # type: ignore[misc]
    assert event == "Sell"
    assert qty == 1840
    assert price == Decimal("169.66")
    assert amount == Decimal("312174.40")


def test_parse_rejects_liquid_style_qty_only() -> None:
    assert parse_change_note("Sell 5505") is None
    assert parse_change_note("Less 2774") is None
    assert parse_change_note("Split 10:1 so quantity 10 times") is None
