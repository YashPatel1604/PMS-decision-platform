"""Compute price return metrics from daily_prices table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.daily_price import DailyPrice
from pms_platform.models.valuation_snapshot import ValuationSnapshot

_HUNDRED = Decimal("100")

# Approximate calendar-day lookback for each return period.
_PERIOD_DAYS: dict[str, int] = {
    "1m": 31,
    "3m": 92,
    "6m": 184,
    "1y": 365,
    "3y": 365 * 3,
}


@dataclass(frozen=True)
class PriceReturnResult:
    """Computed price return metrics for one identifier."""

    identifier_type: str
    identifier: str
    return_1m_pct: Decimal | None
    return_3m_pct: Decimal | None
    return_6m_pct: Decimal | None
    return_1y_pct: Decimal | None
    return_3y_pct: Decimal | None
    all_time_high: Decimal | None
    latest_date: date | None
    latest_close: Decimal | None


def _pct_return(current: Decimal, prior: Decimal) -> Decimal | None:
    if prior == 0:
        return None
    return ((current - prior) / prior * _HUNDRED).quantize(Decimal("0.0001"))


def compute_price_returns(
    prices: list[DailyPrice],
    *,
    reference_date: date | None = None,
) -> PriceReturnResult | None:
    """Compute return metrics from a sorted list of DailyPrice rows.

    Rows must all share the same (identifier_type, identifier).
    """
    if not prices:
        return None

    identifier_type = prices[0].identifier_type
    identifier = prices[0].identifier
    ref = reference_date or date.today()

    # Sort ascending by trade_date; use adjusted_close for returns.
    sorted_prices = sorted(prices, key=lambda p: p.trade_date)
    latest = sorted_prices[-1]
    current_close = latest.adjusted_close
    all_time_high: Decimal = max(p.close for p in sorted_prices)

    def closest_close(lookback_days: int) -> Decimal | None:
        target = ref - timedelta(days=lookback_days)
        # Find the price row closest to (but not after) target date.
        candidates = [p for p in sorted_prices if p.trade_date <= target]
        if not candidates:
            return None
        return candidates[-1].adjusted_close

    return PriceReturnResult(
        identifier_type=identifier_type,
        identifier=identifier,
        return_1m_pct=_pct_return(current_close, c) if (c := closest_close(31)) else None,
        return_3m_pct=_pct_return(current_close, c) if (c := closest_close(92)) else None,
        return_6m_pct=_pct_return(current_close, c) if (c := closest_close(184)) else None,
        return_1y_pct=_pct_return(current_close, c) if (c := closest_close(365)) else None,
        return_3y_pct=_pct_return(current_close, c) if (c := closest_close(365 * 3)) else None,
        all_time_high=all_time_high,
        latest_date=latest.trade_date,
        latest_close=current_close,
    )


def refresh_price_returns(
    session: Session,
    identifier_pairs: list[tuple[str, str]],
    *,
    reference_date: date | None = None,
) -> dict[tuple[str, str], PriceReturnResult]:
    """Compute price returns for each (identifier_type, identifier) pair and upsert into valuation_snapshots."""
    if not identifier_pairs:
        return {}

    ref = reference_date or date.today()
    results: dict[tuple[str, str], PriceReturnResult] = {}

    for identifier_type, identifier in identifier_pairs:
        prices = session.scalars(
            select(DailyPrice)
            .where(
                DailyPrice.identifier_type == identifier_type,
                DailyPrice.identifier == identifier,
            )
            .order_by(DailyPrice.trade_date)
        ).all()

        result = compute_price_returns(list(prices), reference_date=ref)
        if result is None:
            continue

        results[(identifier_type, identifier)] = result

        # Upsert into valuation_snapshots
        existing = session.scalar(
            select(ValuationSnapshot).where(
                ValuationSnapshot.identifier_type == identifier_type,
                ValuationSnapshot.identifier == identifier,
                ValuationSnapshot.as_of_date == ref,
            )
        )
        if existing is not None:
            existing.return_1m_pct = result.return_1m_pct
            existing.return_3m_pct = result.return_3m_pct
            existing.return_6m_pct = result.return_6m_pct
            existing.return_1y_pct = result.return_1y_pct
            existing.return_3y_pct = result.return_3y_pct
            existing.all_time_high = result.all_time_high
        else:
            session.add(
                ValuationSnapshot(
                    identifier_type=identifier_type,
                    identifier=identifier,
                    as_of_date=ref,
                    return_1m_pct=result.return_1m_pct,
                    return_3m_pct=result.return_3m_pct,
                    return_6m_pct=result.return_6m_pct,
                    return_1y_pct=result.return_1y_pct,
                    return_3y_pct=result.return_3y_pct,
                    all_time_high=result.all_time_high,
                    provider="price_history",
                )
            )

    session.flush()
    return results
