"""Transaction-to-market price unit normalization tests."""

from decimal import Decimal

from pms_platform.analytics.price_units import (
    normalize_transaction_price,
    transaction_price_in_series_units,
)


def test_eicher_first_buy_is_scaled_by_ten_for_price_series() -> None:
    normalized = transaction_price_in_series_units(
        Decimal("2958"),
        Decimal("306.20"),
    )
    assert normalized == Decimal("295.8")


def test_same_unit_transaction_price_is_not_rebased_to_market_close() -> None:
    normalized = transaction_price_in_series_units(
        Decimal("100"),
        Decimal("103"),
    )
    assert normalized == Decimal("100")


def test_saregama_first_buy_is_scaled_by_ten() -> None:
    normalized = transaction_price_in_series_units(
        Decimal("851.35"),
        Decimal("84.55"),
    )
    assert normalized == Decimal("85.135")


def test_ambiguous_unit_factor_is_rejected_for_loss_triggers() -> None:
    audit = normalize_transaction_price(
        Decimal("100"),
        Decimal("7"),
    )
    assert audit is not None
    assert audit.status == "REVIEW"
    assert transaction_price_in_series_units(Decimal("100"), Decimal("7")) is None
