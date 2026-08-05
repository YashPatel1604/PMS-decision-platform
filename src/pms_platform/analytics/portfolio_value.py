"""Portfolio market-value helpers for period-return calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.portfolio.position_engine import (
    compute_quantities_as_of,
    cumulative_split_bonus_factors_after,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_DAYS_PER_YEAR = Decimal("365")


@dataclass(frozen=True)
class PortfolioPeriodReturn:
    """Portfolio return over an aligned date window."""

    start_date: date
    end_date: date
    start_value: Decimal
    end_value: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal | None
    methodology: str


def equity_portfolio_market_value(session: Session, as_of_date: date) -> Decimal | None:
    """Value all equity holdings using adjusted closes on or before a date.

    Quantities are scaled by later SPLIT/BONUS factors so they stay consistent
    with vendor split-adjusted closes.
    """
    quantities = compute_quantities_as_of(session, as_of_date)
    if not quantities:
        return _ZERO

    factors = cumulative_split_bonus_factors_after(
        session, as_of_date, security_ids=set(quantities)
    )
    total = _ZERO
    priced_holdings = 0
    for security_id, quantity in quantities.items():
        observation = lookup_daily_price(session, security_id, as_of_date)
        if observation is None:
            continue
        factor = factors.get(security_id, _ONE)
        total += observation.adjusted_close * Decimal(quantity) * factor
        priced_holdings += 1

    if priced_holdings == 0:
        return None
    return total


def compute_portfolio_period_return(
    session: Session,
    *,
    start_date: date,
    end_date: date,
) -> PortfolioPeriodReturn | None:
    """Compute portfolio return over the same window as a stock comparison.

    Prefer official calendar-year TWR from ``CAGR_PMS`` (contribution-neutral).
    Fall back to reconstructed equity MV start→end only when the calendar is
    unavailable (that fallback is *not* a true investment return when capital
    was added during the window).
    """
    from pms_platform.analytics.portfolio_calendar_returns import (
        linked_portfolio_return_pct,
    )

    linked = linked_portfolio_return_pct(start_date, end_date)
    if linked is not None:
        holding_days = max((end_date - start_date).days, 0)
        annualized: Decimal | None
        if holding_days <= 0:
            annualized = None
        else:
            growth = _ONE + (linked / _HUNDRED)
            exponent = _DAYS_PER_YEAR / Decimal(holding_days)
            annualized = ((growth**exponent) - _ONE) * _HUNDRED
        return PortfolioPeriodReturn(
            start_date=start_date,
            end_date=end_date,
            start_value=_ZERO,
            end_value=_ZERO,
            total_return_pct=linked,
            annualized_return_pct=annualized,
            methodology="VALUES_NAV_OR_CAGR_TWR",
        )

    start_value = equity_portfolio_market_value(session, start_date)
    end_value = equity_portfolio_market_value(session, end_date)
    if start_value is None or end_value is None or start_value <= 0:
        return None

    total_return = ((end_value / start_value) - _ONE) * _HUNDRED
    holding_days = max((end_date - start_date).days, 0)
    annualized = None
    if holding_days > 0:
        growth = _ONE + (total_return / _HUNDRED)
        exponent = _DAYS_PER_YEAR / Decimal(holding_days)
        annualized = ((growth**exponent) - _ONE) * _HUNDRED

    return PortfolioPeriodReturn(
        start_date=start_date,
        end_date=end_date,
        start_value=start_value,
        end_value=end_value,
        total_return_pct=total_return,
        annualized_return_pct=annualized,
        methodology="EQUITY_MARKET_VALUE_START_END",
    )


def list_security_trading_dates(
    session: Session,
    security_id: str,
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return distinct trade dates for one security inside a window."""
    from pms_platform.models import DailyPrice

    rows = session.scalars(
        select(DailyPrice.trade_date)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date >= start_date,
            DailyPrice.trade_date <= end_date,
        )
        .distinct()
        .order_by(DailyPrice.trade_date)
    ).all()
    return list(rows)
