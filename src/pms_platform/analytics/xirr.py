"""XIRR calculation for dated cash flows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from scipy.optimize import brentq

_DAYS_PER_YEAR = Decimal("365")
_MIN_RATE = Decimal("-0.9999")
_MAX_RATE = Decimal("10")


def compute_xirr(cash_flows: list[tuple[date, Decimal]]) -> Decimal | None:
    """Return the annualized internal rate of return for dated cash flows.

    Cash outflows must be negative and inflows positive. Returns ``None`` when
    the calculation is undefined or does not converge.
    """
    if len(cash_flows) < 2:
        return None

    amounts = [amount for _, amount in cash_flows]
    if not any(amount < 0 for amount in amounts) or not any(amount > 0 for amount in amounts):
        return None

    ordered = sorted(cash_flows, key=lambda item: item[0])
    start_date = ordered[0][0]
    day_offsets = [Decimal((flow_date - start_date).days) for flow_date, _ in ordered]
    float_amounts = [float(amount) for _, amount in ordered]
    float_offsets = [float(offset) for offset in day_offsets]

    def npv(rate: float) -> float:
        return sum(
            amount / ((1.0 + rate) ** (offset / float(_DAYS_PER_YEAR)))
            for amount, offset in zip(float_amounts, float_offsets, strict=True)
        )

    try:
        solved = brentq(npv, float(_MIN_RATE), float(_MAX_RATE))
    except ValueError:
        return None

    return Decimal(str(round(solved, 8)))
