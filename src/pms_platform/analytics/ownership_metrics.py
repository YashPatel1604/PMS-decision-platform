"""Ownership-period path metrics for a single episode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from pms_platform.analytics.portfolio_value import list_security_trading_dates
from pms_platform.market_data.lookup import lookup_benchmark_tri, lookup_daily_price
from pms_platform.models import DecisionEvent

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class EpisodeCostState:
    """Episode-scoped quantity and average cost."""

    quantity: int
    average_cost: Decimal


@dataclass(frozen=True)
class OwnershipMetrics:
    """Path-based metrics while an episode was open."""

    max_drawdown_pct: Decimal | None
    max_unrealized_gain_pct: Decimal | None
    days_below_cost: int
    days_underperforming_benchmark: int
    notes: tuple[str, ...]


def _episode_cost_states(events: list[DecisionEvent]) -> dict[date, EpisodeCostState]:
    total_cost = _ZERO
    states: dict[date, EpisodeCostState] = {}

    for event in events:
        if event.decision_type in {"INITIATE", "ADD"}:
            if event.price is not None and event.quantity_change > 0:
                total_cost += event.price * Decimal(event.quantity_change)
        elif event.decision_type in {"REDUCE", "EXIT"} and event.position_before > 0:
            sell_qty = abs(event.quantity_change)
            removed_cost = (Decimal(sell_qty) / Decimal(event.position_before)) * total_cost
            total_cost -= removed_cost

        quantity = event.position_after
        if quantity > 0:
            average_cost = total_cost / Decimal(quantity) if total_cost > 0 else _ZERO
            states[event.event_date] = EpisodeCostState(
                quantity=quantity,
                average_cost=average_cost,
            )

    return states


def _cost_state_on_date(
    states: dict[date, EpisodeCostState],
    as_of_date: date,
) -> EpisodeCostState | None:
    current: EpisodeCostState | None = None
    for state_date, state in sorted(states.items()):
        if state_date > as_of_date:
            break
        current = state
    return current


def compute_ownership_metrics(
    session: Session,
    *,
    security_id: str,
    entry_date: date,
    exit_date: date,
    events: list[DecisionEvent],
    benchmark_code: str,
) -> OwnershipMetrics:
    """Compute drawdown and underwater-day metrics for a closed episode."""
    notes: list[str] = []
    cost_states = _episode_cost_states(events)
    trading_dates = list_security_trading_dates(session, security_id, entry_date, exit_date)

    entry_price_obs = lookup_daily_price(session, security_id, entry_date)
    entry_benchmark_obs = lookup_benchmark_tri(session, benchmark_code, entry_date)
    if entry_price_obs is None:
        notes.append("Missing entry price for ownership metrics")
    if entry_benchmark_obs is None:
        notes.append("Missing entry benchmark for ownership metrics")

    peak_price: Decimal | None = None
    max_drawdown = _ZERO
    max_unrealized_gain = _ZERO
    days_below_cost = 0
    days_underperforming = 0
    evaluated_days = 0

    for trade_date in trading_dates:
        cost_state = _cost_state_on_date(cost_states, trade_date)
        if cost_state is None or cost_state.quantity <= 0:
            continue

        price_obs = lookup_daily_price(session, security_id, trade_date)
        if price_obs is None:
            continue

        price = price_obs.adjusted_close
        evaluated_days += 1
        peak_price = price if peak_price is None else max(peak_price, price)
        if peak_price and peak_price > 0:
            drawdown = ((peak_price - price) / peak_price) * _HUNDRED
            max_drawdown = max(max_drawdown, drawdown)

        if cost_state.average_cost > 0:
            unrealized_gain = ((price / cost_state.average_cost) - _ONE) * _HUNDRED
            max_unrealized_gain = max(max_unrealized_gain, unrealized_gain)
            if price < cost_state.average_cost:
                days_below_cost += 1

        if entry_price_obs is not None and entry_benchmark_obs is not None:
            bench_obs = lookup_benchmark_tri(session, benchmark_code, trade_date)
            if bench_obs is not None and entry_price_obs.adjusted_close > 0:
                stock_return = (price / entry_price_obs.adjusted_close) - _ONE
                bench_return = (bench_obs.tri_level / entry_benchmark_obs.tri_level) - _ONE
                if stock_return < bench_return:
                    days_underperforming += 1

    if evaluated_days == 0:
        notes.append("No in-episode trading-day prices available")

    return OwnershipMetrics(
        max_drawdown_pct=max_drawdown if evaluated_days else None,
        max_unrealized_gain_pct=max_unrealized_gain if evaluated_days else None,
        days_below_cost=days_below_cost,
        days_underperforming_benchmark=days_underperforming,
        notes=tuple(notes),
    )
