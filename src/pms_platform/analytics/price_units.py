"""Normalize transaction prices into historical daily-price series units."""

from dataclasses import dataclass
from decimal import Decimal
from math import log

_HUNDRED = Decimal("100")
_MAX_ENTRY_DEVIATION_PCT = Decimal("15")
_COMMON_CORPORATE_ACTION_FACTORS = (
    Decimal("0.025"),
    Decimal("0.04"),
    Decimal("0.05"),
    Decimal("0.1"),
    Decimal("0.125"),
    Decimal("0.2"),
    Decimal("0.25"),
    Decimal("0.3333333333"),
    Decimal("0.4"),
    Decimal("0.5"),
    Decimal("0.6"),
    Decimal("0.625"),
    Decimal("0.6666666667"),
    Decimal("0.75"),
    Decimal("0.8"),
    Decimal("1"),
    Decimal("1.25"),
    Decimal("1.5"),
    Decimal("2"),
    Decimal("2.5"),
    Decimal("3"),
    Decimal("4"),
    Decimal("5"),
    Decimal("10"),
)


@dataclass(frozen=True)
class PriceUnitNormalization:
    """Auditable first-buy conversion result."""

    transaction_price: Decimal
    market_price_in_series_units: Decimal
    inferred_factor: Decimal
    normalized_transaction_price: Decimal
    entry_deviation_pct: Decimal
    status: str


def infer_transaction_to_series_factor(
    transaction_price: Decimal,
    market_price_in_series_units: Decimal,
) -> Decimal | None:
    """Infer a split/bonus unit factor from same-date transaction and market prices.

    Transaction history can retain pre-corporate-action units while imported
    market history is back-adjusted. The observed market/transaction ratio is
    snapped to the nearest common corporate-action factor so the transaction's
    execution premium or discount is preserved instead of replacing the first
    buy price with that day's market close.
    """
    if transaction_price <= 0 or market_price_in_series_units <= 0:
        return None
    observed = market_price_in_series_units / transaction_price
    return min(
        _COMMON_CORPORATE_ACTION_FACTORS,
        key=lambda factor: abs(log(float(observed / factor))),
    )


def transaction_price_in_series_units(
    transaction_price: Decimal,
    market_price_in_series_units: Decimal,
) -> Decimal | None:
    """Return a transaction price expressed in the daily-price series' units."""
    result = normalize_transaction_price(
        transaction_price,
        market_price_in_series_units,
    )
    return (
        result.normalized_transaction_price
        if result is not None and result.status == "OK"
        else None
    )


def normalize_transaction_price(
    transaction_price: Decimal,
    market_price_in_series_units: Decimal,
) -> PriceUnitNormalization | None:
    """Normalize and validate one transaction-to-market unit conversion."""
    factor = infer_transaction_to_series_factor(
        transaction_price,
        market_price_in_series_units,
    )
    if factor is None:
        return None
    normalized = transaction_price * factor
    deviation = (
        abs(normalized - market_price_in_series_units)
        / market_price_in_series_units
        * _HUNDRED
    )
    return PriceUnitNormalization(
        transaction_price=transaction_price,
        market_price_in_series_units=market_price_in_series_units,
        inferred_factor=factor,
        normalized_transaction_price=normalized,
        entry_deviation_pct=deviation,
        status="OK" if deviation <= _MAX_ENTRY_DEVIATION_PCT else "REVIEW",
    )
