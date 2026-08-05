"""Ownership-period path metrics for a single episode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from pms_platform.analytics.exit_assessment import missed_upside_vs_peak_pct
from pms_platform.analytics.portfolio_value import list_security_trading_dates
from pms_platform.analytics.price_units import transaction_price_in_series_units
from pms_platform.market_data.lookup import lookup_benchmark_tri, lookup_daily_price
from pms_platform.models import DecisionEvent

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")

LOSS_HOLD_STAYED_UNDERWATER = "STAYED_UNDERWATER"
LOSS_HOLD_RODE_WINNER_DOWN = "RODE_WINNER_DOWN"
RECOVERED_AFTER_LONG_LOSS = "RECOVERED_AFTER_LONG_LOSS"
LONG_UNDERWATER_MIN_CALENDAR_DAYS = 365


@dataclass(frozen=True)
class EpisodeCostState:
    """Holding quantity and fixed first-buy threshold in price-series units."""

    quantity: int
    first_buy_price: Decimal


@dataclass(frozen=True)
class OwnershipMetrics:
    """Path-based metrics while an episode was open."""

    max_drawdown_pct: Decimal | None
    max_unrealized_gain_pct: Decimal | None
    peak_price: Decimal | None
    peak_price_date: date | None
    exit_adjusted_close: Decimal | None
    missed_upside_vs_peak_pct: Decimal | None
    ownership_trading_days: int
    days_below_cost: int
    days_underperforming_benchmark: int
    first_below_cost_date: date | None
    days_held_after_first_loss: int
    calendar_days_held_after_first_loss: int | None
    was_profitable_before_loss: bool
    loss_hold_pattern: str | None
    notes: tuple[str, ...]


def _episode_first_buy_states(
    session: Session,
    security_id: str,
    events: list[DecisionEvent],
) -> dict[date, EpisodeCostState]:
    """Track one immutable INITIATE price through the episode.

    ADD transactions never change the threshold. The first transaction price
    is converted into daily-price-series units using the inferred corporate
    action factor at entry.
    """
    first_buy_price: Decimal | None = None
    states: dict[date, EpisodeCostState] = {}

    for event in events:
        if (
            first_buy_price is None
            and event.decision_type == "INITIATE"
            and event.price is not None
            and event.price > 0
            and event.quantity_change > 0
        ):
            market = lookup_daily_price(session, security_id, event.event_date)
            if market is not None:
                first_buy_price = transaction_price_in_series_units(
                    event.price,
                    market.adjusted_close,
                    security_id=security_id,
                    as_of=event.event_date,
                )

        quantity = event.position_after
        if quantity > 0 and first_buy_price is not None:
            states[event.event_date] = EpisodeCostState(
                quantity=quantity,
                first_buy_price=first_buy_price,
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
    sold_at_loss: bool,
) -> OwnershipMetrics:
    """Compute drawdown and underwater-day metrics for a closed episode.

    A day is underwater only when market price is below the split-adjusted
    first INITIATE price. Later buys never change the threshold.
    """
    notes: list[str] = []
    cost_states = _episode_first_buy_states(session, security_id, events)
    trading_dates = list_security_trading_dates(session, security_id, entry_date, exit_date)

    entry_price_obs = lookup_daily_price(session, security_id, entry_date)
    entry_benchmark_obs = lookup_benchmark_tri(session, benchmark_code, entry_date)
    if entry_price_obs is None:
        notes.append("Missing entry price for ownership metrics")
    if entry_benchmark_obs is None:
        notes.append("Missing entry benchmark for ownership metrics")
    if not cost_states:
        notes.append("Missing first-buy basis for underwater metrics")

    peak_price: Decimal | None = None
    peak_price_date: date | None = None
    max_drawdown = _ZERO
    max_unrealized_gain = _ZERO
    days_below_cost = 0
    days_underperforming = 0
    evaluated_days = 0

    ever_above_cost = False
    final_stretch_start: date | None = None
    stretch_was_profitable_before = False
    days_held_in_final_stretch = 0

    current_stretch_start: date | None = None
    last_underwater_date: date | None = None
    current_stretch_trading_days = 0
    longest_stretch_start: date | None = None
    longest_stretch_calendar_days = 0
    longest_stretch_trading_days = 0

    def _maybe_record_longest_stretch() -> None:
        nonlocal longest_stretch_start, longest_stretch_calendar_days, longest_stretch_trading_days
        if current_stretch_start is None or last_underwater_date is None:
            return
        calendar_len = (last_underwater_date - current_stretch_start).days
        if calendar_len > longest_stretch_calendar_days or (
            calendar_len == longest_stretch_calendar_days
            and current_stretch_trading_days > longest_stretch_trading_days
        ):
            longest_stretch_start = current_stretch_start
            longest_stretch_calendar_days = calendar_len
            longest_stretch_trading_days = current_stretch_trading_days

    def _clear_current_stretch() -> None:
        nonlocal current_stretch_start, last_underwater_date, current_stretch_trading_days
        _maybe_record_longest_stretch()
        current_stretch_start = None
        last_underwater_date = None
        current_stretch_trading_days = 0

    for trade_date in trading_dates:
        cost_state = _cost_state_on_date(cost_states, trade_date)
        if cost_state is None or cost_state.quantity <= 0:
            continue

        price_obs = lookup_daily_price(session, security_id, trade_date)
        if price_obs is None:
            continue

        price = price_obs.adjusted_close
        buy_cost = cost_state.first_buy_price
        evaluated_days += 1
        peak_price = price if peak_price is None else max(peak_price, price)
        if peak_price == price:
            peak_price_date = trade_date
        if peak_price and peak_price > 0:
            drawdown = ((peak_price - price) / peak_price) * _HUNDRED
            max_drawdown = max(max_drawdown, drawdown)

        if buy_cost > 0:
            unrealized_gain = ((price / buy_cost) - _ONE) * _HUNDRED
            max_unrealized_gain = max(max_unrealized_gain, unrealized_gain)

            if price < buy_cost:
                if final_stretch_start is None:
                    final_stretch_start = trade_date
                    stretch_was_profitable_before = ever_above_cost
                if current_stretch_start is None:
                    current_stretch_start = trade_date
                last_underwater_date = trade_date
                current_stretch_trading_days += 1
                days_below_cost += 1
            else:
                # At or above the first buy price — not a loss day.
                ever_above_cost = True
                final_stretch_start = None
                _clear_current_stretch()

        if final_stretch_start is not None and trade_date >= final_stretch_start:
            days_held_in_final_stretch += 1

        if entry_price_obs is not None and entry_benchmark_obs is not None:
            bench_obs = lookup_benchmark_tri(session, benchmark_code, trade_date)
            if bench_obs is not None and entry_price_obs.adjusted_close > 0:
                stock_return = (price / entry_price_obs.adjusted_close) - _ONE
                bench_return = (bench_obs.tri_level / entry_benchmark_obs.tri_level) - _ONE
                if stock_return < bench_return:
                    days_underperforming += 1

    _maybe_record_longest_stretch()

    if evaluated_days == 0:
        notes.append("No in-episode trading-day prices available")

    exit_obs = lookup_daily_price(session, security_id, exit_date)
    exit_price = exit_obs.adjusted_close if exit_obs else None
    missed = (
        missed_upside_vs_peak_pct(peak_price, exit_price)
        if peak_price is not None and exit_price is not None
        else None
    )

    loss_hold_start: date | None = None
    loss_hold_trading_days = 0
    loss_hold_calendar_days: int | None = None
    loss_hold_pattern: str | None = None
    was_profitable_before_loss = False

    if sold_at_loss and final_stretch_start is not None:
        loss_hold_start = final_stretch_start
        loss_hold_trading_days = days_held_in_final_stretch
        loss_hold_calendar_days = (exit_date - final_stretch_start).days
        was_profitable_before_loss = stretch_was_profitable_before
        loss_hold_pattern = (
            LOSS_HOLD_RODE_WINNER_DOWN
            if stretch_was_profitable_before
            else LOSS_HOLD_STAYED_UNDERWATER
        )
    elif (
        not sold_at_loss
        and longest_stretch_start is not None
        and longest_stretch_calendar_days >= LONG_UNDERWATER_MIN_CALENDAR_DAYS
    ):
        loss_hold_start = longest_stretch_start
        loss_hold_trading_days = longest_stretch_trading_days
        loss_hold_calendar_days = longest_stretch_calendar_days
        loss_hold_pattern = RECOVERED_AFTER_LONG_LOSS

    return OwnershipMetrics(
        max_drawdown_pct=max_drawdown if evaluated_days else None,
        max_unrealized_gain_pct=max_unrealized_gain if evaluated_days else None,
        peak_price=peak_price,
        peak_price_date=peak_price_date,
        exit_adjusted_close=exit_price,
        missed_upside_vs_peak_pct=missed,
        ownership_trading_days=evaluated_days,
        days_below_cost=days_below_cost,
        days_underperforming_benchmark=days_underperforming,
        first_below_cost_date=loss_hold_start,
        days_held_after_first_loss=loss_hold_trading_days,
        calendar_days_held_after_first_loss=loss_hold_calendar_days,
        was_profitable_before_loss=was_profitable_before_loss,
        loss_hold_pattern=loss_hold_pattern,
        notes=tuple(notes),
    )
