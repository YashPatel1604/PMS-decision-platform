"""XIRR calculation for dated cash flows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

_DAYS_PER_YEAR = Decimal("365")
_MIN_RATE = -0.9999
_MAX_RATE = 10.0


def _brentq(fn, lo: float, hi: float, *, tol: float = 1e-12, max_iter: int = 100) -> float:
    """Bracketed root find (Brent-style bisection fallback)."""
    flo, fhi = fn(lo), fn(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0.0:
        raise ValueError("root not bracketed")
    a, b, fa, fb = lo, hi, flo, fhi
    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        fmid = fn(mid)
        if abs(fmid) < tol or abs(b - a) < tol:
            return mid
        if fa * fmid <= 0.0:
            b, fb = mid, fmid
        else:
            a, fa = mid, fmid
    return 0.5 * (a + b)


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
        solved = _brentq(npv, _MIN_RATE, _MAX_RATE)
    except ValueError:
        return None

    return Decimal(str(round(solved, 8)))
