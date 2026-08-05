"""Backtest selling after one year below the first purchase price."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.price_units import transaction_price_in_series_units
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import DailyPrice, DecisionEvent, InvestmentEpisode, Security
from pms_platform.models.enums import EpisodeStatus
from pms_platform.portfolio.position_engine import compute_quantities_as_of

_ONE = Decimal("1")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0")
_TRIGGER_DAYS = 365
_TIE_EPSILON_PP = Decimal("0.5")


@dataclass(frozen=True)
class ContinuousLossEpisodeResult:
    """One closed episode under the continuous-loss diversification rule."""

    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: date
    exit_date: date
    status: str
    initial_purchase_price: Decimal | None = None
    adjusted_initial_price_threshold: Decimal | None = None
    underwater_start_date: date | None = None
    trigger_date: date | None = None
    measurement_days: int | None = None
    trigger_quantity: int | None = None
    trigger_price: Decimal | None = None
    trigger_proceeds: Decimal | None = None
    common_end_date: date | None = None
    stock_return_pct: Decimal | None = None
    diversified_return_pct: Decimal | None = None
    return_uplift_pct: Decimal | None = None
    stock_cagr_pct: Decimal | None = None
    diversified_cagr_pct: Decimal | None = None
    annualized_advantage_pp: Decimal | None = None
    stock_end_value: Decimal | None = None
    diversified_end_value: Decimal | None = None
    impact_rupees: Decimal | None = None
    impact_pct_of_trigger: Decimal | None = None
    trigger_portfolio_value: Decimal | None = None
    trigger_equity_value: Decimal | None = None
    trigger_liquid_value: Decimal | None = None
    portfolio_denominator_status: str | None = None
    position_weight_pct: Decimal | None = None
    hold_portfolio_contribution_pct: Decimal | None = None
    diversified_portfolio_contribution_pct: Decimal | None = None
    portfolio_impact_pp: Decimal | None = None
    other_holdings_count: int = 0
    priced_holdings_count: int = 0
    missing_price_holdings_count: int = 0
    absolute_contribution_share_pct: Decimal | None = None
    leave_one_out_impact_rupees: Decimal | None = None
    leave_one_out_impact_pct: Decimal | None = None
    leave_one_out_stock_xirr: Decimal | None = None
    leave_one_out_diversified_xirr: Decimal | None = None
    leave_one_out_annualized_advantage_pp: Decimal | None = None
    leave_one_out_mean_portfolio_impact_pp: Decimal | None = None
    leave_one_out_median_portfolio_impact_pp: Decimal | None = None
    leave_one_out_mean_return_advantage_pp: Decimal | None = None
    leave_one_out_median_return_advantage_pp: Decimal | None = None
    removal_flips_result: bool = False
    note: str | None = None


@dataclass(frozen=True)
class ContinuousLossBacktestResult:
    """Aggregate result and auditable episode-level calculations."""

    methodology: str
    closed_episodes: int
    triggered_episodes: int
    no_trigger_episodes: int
    excluded_episodes: int
    trigger_rate_pct: Decimal
    total_trigger_proceeds: Decimal
    common_end_date: date | None
    stock_end_value: Decimal
    diversified_end_value: Decimal
    net_impact_rupees: Decimal
    stock_xirr: Decimal | None
    diversified_xirr: Decimal | None
    annualized_advantage_pp: Decimal | None
    terminal_value_uplift_pct: Decimal | None
    mean_portfolio_impact_pp: Decimal | None
    median_portfolio_impact_pp: Decimal | None
    largest_portfolio_impact_pp: Decimal | None
    equal_capital_start_value: Decimal
    hold_equal_capital_end_value: Decimal
    diversified_equal_capital_end_value: Decimal
    equal_capital_net_difference: Decimal
    mean_return_advantage_pp: Decimal | None
    median_return_advantage_pp: Decimal | None
    average_winner_pp: Decimal | None
    average_loser_pp: Decimal | None
    payoff_ratio: Decimal | None
    profit_factor: Decimal | None
    positive_effect_sum_pp: Decimal
    negative_effect_sum_pp: Decimal
    historical_capital_weighted_uplift_pct: Decimal | None
    stock_return_pct: Decimal | None
    diversified_return_pct: Decimal | None
    return_uplift_pct: Decimal | None
    positive_episodes: int
    negative_episodes: int
    tie_episodes: int
    positive_episode_rate_pct: Decimal | None
    tie_episode_rate_pct: Decimal | None
    top_episode_contribution_pct: Decimal | None
    top_three_contribution_pct: Decimal | None
    contribution_hhi: Decimal | None
    conclusion: str
    conclusion_text: str
    loo_min_mean_return_advantage_pp: Decimal | None
    loo_max_mean_return_advantage_pp: Decimal | None
    loo_positive_fraction_pct: Decimal | None
    episodes: tuple[ContinuousLossEpisodeResult, ...]


def _first_initiate(events: list[DecisionEvent]) -> DecisionEvent | None:
    return next(
        (
            event
            for event in sorted(
                events,
                key=lambda row: (row.event_date, row.decision_event_id),
            )
            if event.decision_type == "INITIATE"
            and event.price is not None
            and event.price > 0
            and event.quantity_change > 0
        ),
        None,
    )


def _adjusted_initial_threshold(
    session: Session,
    security_id: str,
    initiate: DecisionEvent,
) -> Decimal | None:
    """Convert the first execution price into adjusted-price-series units."""
    observation = lookup_daily_price(session, security_id, initiate.event_date)
    if observation is None or initiate.price is None or initiate.price <= 0:
        return None
    return transaction_price_in_series_units(
        initiate.price,
        observation.adjusted_close,
        security_id=security_id,
        as_of=initiate.event_date,
    )


def _episode_price_path(
    session: Session,
    security_id: str,
    start_date: date,
    end_date: date,
) -> list[DailyPrice]:
    rows = session.scalars(
        select(DailyPrice)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date >= start_date,
            DailyPrice.trade_date <= end_date,
        )
        .order_by(DailyPrice.trade_date, DailyPrice.daily_price_id)
    ).all()
    by_date: dict[date, DailyPrice] = {}
    for row in rows:
        by_date[row.trade_date] = row
    return list(by_date.values())


def _continuous_loss_trigger(
    price_path: list[DailyPrice],
    threshold: Decimal,
) -> tuple[date | None, DailyPrice | None]:
    """Return the first 365-calendar-day uninterrupted underwater trigger."""
    stretch_start: date | None = None
    for observation in price_path:
        if observation.adjusted_close < threshold:
            if stretch_start is None:
                stretch_start = observation.trade_date
            if observation.trade_date >= stretch_start + timedelta(days=_TRIGGER_DAYS):
                return stretch_start, observation
        else:
            stretch_start = None
    return None, None


def _position_on_date(events: list[DecisionEvent], as_of_date: date) -> int:
    position = 0
    for event in sorted(
        events,
        key=lambda row: (row.event_date, row.decision_event_id),
    ):
        if event.event_date > as_of_date:
            break
        position = event.position_after
    return position


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, start=_ZERO) / Decimal(len(values)) if values else None


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _equal_capital_values(
    return_pairs: list[tuple[Decimal, Decimal]],
) -> tuple[Decimal, Decimal, Decimal]:
    """Value one hypothetical ₹100 allocation for every triggered episode."""
    start_value = Decimal("100") * Decimal(len(return_pairs))
    hold_end = sum(
        (Decimal("100") * (_ONE + stock_return / _HUNDRED) for stock_return, _ in return_pairs),
        start=_ZERO,
    )
    diversified_end = sum(
        (
            Decimal("100") * (_ONE + diversified_return / _HUNDRED)
            for _, diversified_return in return_pairs
        ),
        start=_ZERO,
    )
    return start_value, hold_end, diversified_end


def _mean_winners(values: list[Decimal]) -> Decimal | None:
    winners = [value for value in values if value > _TIE_EPSILON_PP]
    return _mean(winners)


def _mean_losers(values: list[Decimal]) -> Decimal | None:
    losers = [value for value in values if value < -_TIE_EPSILON_PP]
    return _mean(losers)


def _return_between(
    session: Session,
    security_id: str,
    start_date: date,
    end_date: date,
) -> Decimal | None:
    start_security_id = resolve_price_security_id(session, security_id, start_date)
    end_security_id = resolve_price_security_id(session, security_id, end_date)
    start = lookup_daily_price(session, start_security_id, start_date)
    end = lookup_daily_price(session, end_security_id, end_date)
    if start is None or end is None or start.adjusted_close <= 0:
        return None
    return ((end.adjusted_close / start.adjusted_close) - _ONE) * _HUNDRED


def _annualized_return_pct(total_return_pct: Decimal, measurement_days: int) -> Decimal | None:
    """Annualize one proceeds bucket over its actual measurement period."""
    if measurement_days <= 0:
        return None
    growth_factor = _ONE + total_return_pct / _HUNDRED
    if growth_factor <= 0:
        return None
    years = Decimal(measurement_days) / Decimal("365")
    annualized = float(growth_factor) ** (1.0 / float(years)) - 1.0
    return Decimal(str(annualized)) * _HUNDRED


def _diversified_return(
    session: Session,
    sold_security_id: str,
    start_date: date,
    end_date: date,
) -> tuple[Decimal | None, int, int]:
    """Equal-weight other holdings with measurable start and end prices."""
    holdings = {
        security_id: quantity
        for security_id, quantity in compute_quantities_as_of(session, start_date).items()
        if quantity > 0 and security_id != sold_security_id
    }
    if not holdings:
        return None, 0, 0

    returns: list[Decimal] = []
    missing = 0
    for security_id in sorted(holdings):
        constituent_return = _return_between(
            session,
            security_id,
            start_date,
            end_date,
        )
        if constituent_return is None:
            missing += 1
            continue
        returns.append(constituent_return)

    return (
        sum(returns, start=_ZERO) / Decimal(len(returns)) if returns else None,
        len(returns),
        missing,
    )


def _analyze_episode(
    session: Session,
    episode: InvestmentEpisode,
    events: list[DecisionEvent],
    portfolio_name: str,
) -> ContinuousLossEpisodeResult:
    assert episode.exit_date is not None
    base = ContinuousLossEpisodeResult(
        episode_id=episode.episode_id,
        security_id=episode.security_id,
        portfolio_name=portfolio_name,
        entry_date=episode.entry_date,
        exit_date=episode.exit_date,
        status="NO_TRIGGER",
    )
    initiate = _first_initiate(events)
    if initiate is None:
        return replace(
            base,
            status="EXCLUDED_NO_INITIAL_BUY",
            note="No priced INITIATE event was available.",
        )

    threshold = _adjusted_initial_threshold(
        session,
        episode.security_id,
        initiate,
    )
    if threshold is None:
        return replace(
            base,
            status="EXCLUDED_NO_ENTRY_PRICE",
            initial_purchase_price=initiate.price,
            note="The initial purchase price could not be aligned to adjusted prices.",
        )

    path = _episode_price_path(
        session,
        episode.security_id,
        initiate.event_date,
        episode.exit_date,
    )
    underwater_start, trigger = _continuous_loss_trigger(path, threshold)
    if trigger is None:
        return replace(
            base,
            initial_purchase_price=initiate.price,
            adjusted_initial_price_threshold=threshold,
            note="No continuous 365-calendar-day stretch below the initial buy price.",
        )

    quantity = _position_on_date(events, trigger.trade_date)
    if quantity <= 0:
        return replace(
            base,
            status="EXCLUDED_NO_POSITION_AT_TRIGGER",
            initial_purchase_price=initiate.price,
            adjusted_initial_price_threshold=threshold,
            underwater_start_date=underwater_start,
            trigger_date=trigger.trade_date,
            note="No remaining position existed on the trigger date.",
        )

    proceeds = trigger.close * Decimal(quantity)
    stock_return = _return_between(
        session,
        episode.security_id,
        trigger.trade_date,
        episode.exit_date,
    )
    if stock_return is None:
        return replace(
            base,
            status="EXCLUDED_NO_EXIT_PRICE",
            initial_purchase_price=initiate.price,
            adjusted_initial_price_threshold=threshold,
            underwater_start_date=underwater_start,
            trigger_date=trigger.trade_date,
            trigger_quantity=quantity,
            trigger_price=trigger.close,
            trigger_proceeds=proceeds,
            note="The stock return could not be measured through its actual exit.",
        )

    diversified_return, priced_count, missing_count = _diversified_return(
        session,
        episode.security_id,
        trigger.trade_date,
        episode.exit_date,
    )
    other_count = priced_count + missing_count
    if diversified_return is None:
        return replace(
            base,
            status="EXCLUDED_NO_OTHER_HOLDINGS",
            initial_purchase_price=initiate.price,
            adjusted_initial_price_threshold=threshold,
            underwater_start_date=underwater_start,
            trigger_date=trigger.trade_date,
            trigger_quantity=quantity,
            trigger_price=trigger.close,
            trigger_proceeds=proceeds,
            stock_return_pct=stock_return,
            other_holdings_count=other_count,
            note="No other equity holding was available for diversification.",
        )

    stock_end_value = proceeds * (_ONE + stock_return / _HUNDRED)
    diversified_end_value = proceeds * (_ONE + diversified_return / _HUNDRED)
    impact = diversified_end_value - stock_end_value
    measurement_days = (episode.exit_date - trigger.trade_date).days
    stock_cagr = _annualized_return_pct(stock_return, measurement_days)
    diversified_cagr = _annualized_return_pct(diversified_return, measurement_days)
    return replace(
        base,
        status="TRIGGERED",
        initial_purchase_price=initiate.price,
        adjusted_initial_price_threshold=threshold,
        underwater_start_date=underwater_start,
        trigger_date=trigger.trade_date,
        measurement_days=measurement_days,
        trigger_quantity=quantity,
        trigger_price=trigger.close,
        trigger_proceeds=proceeds,
        stock_return_pct=stock_return,
        diversified_return_pct=diversified_return,
        return_uplift_pct=diversified_return - stock_return,
        stock_cagr_pct=stock_cagr,
        diversified_cagr_pct=diversified_cagr,
        annualized_advantage_pp=(
            diversified_cagr - stock_cagr
            if diversified_cagr is not None and stock_cagr is not None
            else None
        ),
        stock_end_value=stock_end_value,
        diversified_end_value=diversified_end_value,
        impact_rupees=impact,
        impact_pct_of_trigger=(impact / proceeds) * _HUNDRED if proceeds else None,
        other_holdings_count=other_count,
        priced_holdings_count=priced_count,
        missing_price_holdings_count=missing_count,
        note=(
            f"{missing_count} holding(s) were excluded because start/end prices were unavailable."
            if missing_count
            else None
        ),
    )


def _sign(value: Decimal) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _conclusion(
    annualized_advantage_pp: Decimal,
    top_share: Decimal | None,
    any_flip: bool,
) -> tuple[str, str]:
    sensitive = any_flip or (top_share is not None and top_share >= Decimal("50"))
    if annualized_advantage_pp > 0 and sensitive:
        return (
            "POSITIVE_BUT_OUTLIER_SENSITIVE",
            "The rule improved the aggregate result, but one stock can materially change "
            "the conclusion. Treat it as promising rather than proven.",
        )
    if annualized_advantage_pp > 0:
        return (
            "BROADLY_POSITIVE",
            "The rule improved the aggregate result and no single stock reversed that result.",
        )
    if annualized_advantage_pp < 0 and sensitive:
        return (
            "NEGATIVE_BUT_OUTLIER_SENSITIVE",
            "The rule reduced the aggregate result, but the conclusion depends materially "
            "on one stock.",
        )
    if annualized_advantage_pp < 0:
        return (
            "BROADLY_NEGATIVE",
            "The rule reduced the aggregate result and no single stock reversed that result.",
        )
    return "NEUTRAL", "The two strategies produced the same aggregate ending value."


def run_continuous_loss_backtest(session: Session) -> ContinuousLossBacktestResult:
    """Run the first-buy-price continuous-loss rule across all closed episodes."""
    episodes = session.scalars(
        select(InvestmentEpisode)
        .where(
            InvestmentEpisode.status == EpisodeStatus.CLOSED.value,
            InvestmentEpisode.exit_date.is_not(None),
        )
        .order_by(InvestmentEpisode.exit_date, InvestmentEpisode.episode_id)
    ).all()
    episode_ids = [episode.episode_id for episode in episodes]
    events_by_episode: dict[int, list[DecisionEvent]] = {}
    if episode_ids:
        for event in session.scalars(
            select(DecisionEvent)
            .where(DecisionEvent.episode_id.in_(episode_ids))
            .order_by(
                DecisionEvent.episode_id,
                DecisionEvent.event_date,
                DecisionEvent.decision_event_id,
            )
        ).all():
            events_by_episode.setdefault(event.episode_id, []).append(event)

    securities = {
        security.security_id: security for security in session.scalars(select(Security)).all()
    }
    results = [
        _analyze_episode(
            session,
            episode,
            events_by_episode.get(episode.episode_id, []),
            (
                securities[episode.security_id].portfolio_name
                if episode.security_id in securities
                else episode.security_id
            ),
        )
        for episode in episodes
    ]
    triggered = [row for row in results if row.status == "TRIGGERED"]
    total_proceeds = sum(
        (row.trigger_proceeds or _ZERO for row in triggered),
        start=_ZERO,
    )
    stock_end_value = sum(
        (row.stock_end_value or _ZERO for row in triggered),
        start=_ZERO,
    )
    diversified_end_value = sum(
        (row.diversified_end_value or _ZERO for row in triggered),
        start=_ZERO,
    )
    net_impact = diversified_end_value - stock_end_value
    terminal_value_uplift = net_impact / stock_end_value * _HUNDRED if stock_end_value > 0 else None
    stock_return = (
        ((stock_end_value / total_proceeds) - _ONE) * _HUNDRED if total_proceeds > 0 else None
    )
    diversified_return = (
        ((diversified_end_value / total_proceeds) - _ONE) * _HUNDRED if total_proceeds > 0 else None
    )

    return_advantages = [
        row.return_uplift_pct for row in triggered if row.return_uplift_pct is not None
    ]
    mean_return_advantage = _mean(return_advantages)
    median_return_advantage = _median(return_advantages)
    average_winner = _mean_winners(return_advantages)
    average_loser = _mean_losers(return_advantages)
    payoff_ratio = (
        average_winner / abs(average_loser)
        if average_winner is not None
        and average_loser is not None
        and average_loser != 0
        else None
    )
    equal_capital_start, hold_equal_capital_end, diversified_equal_capital_end = (
        _equal_capital_values(
            [
                (row.stock_return_pct or _ZERO, row.diversified_return_pct or _ZERO)
                for row in triggered
            ]
        )
    )
    positive_effect_sum = sum(
        (value for value in return_advantages if value > 0),
        start=_ZERO,
    )
    negative_effect_sum = sum(
        (value for value in return_advantages if value < 0),
        start=_ZERO,
    )
    profit_factor = (
        positive_effect_sum / abs(negative_effect_sum)
        if negative_effect_sum < 0
        else None
    )
    historical_capital_weighted_uplift = (
        net_impact / total_proceeds * _HUNDRED if total_proceeds > 0 else None
    )
    absolute_impact = sum(
        (abs(row.return_uplift_pct or _ZERO) for row in triggered),
        start=_ZERO,
    )
    enriched: list[ContinuousLossEpisodeResult] = []
    for row in results:
        if row.status != "TRIGGERED":
            enriched.append(row)
            continue
        contribution = (
            abs(row.return_uplift_pct or _ZERO) / absolute_impact * _HUNDRED
            if absolute_impact > 0
            else None
        )
        remaining_proceeds = total_proceeds - (row.trigger_proceeds or _ZERO)
        remaining_impact = net_impact - (row.impact_rupees or _ZERO)
        remaining_impact_pct = (
            remaining_impact / remaining_proceeds * _HUNDRED if remaining_proceeds > 0 else None
        )
        remaining_advantages = [
            candidate.return_uplift_pct
            for candidate in triggered
            if candidate.episode_id != row.episode_id and candidate.return_uplift_pct is not None
        ]
        remaining_mean = _mean(remaining_advantages)
        remaining_median = _median(remaining_advantages)
        enriched.append(
            replace(
                row,
                absolute_contribution_share_pct=contribution,
                leave_one_out_impact_rupees=remaining_impact,
                leave_one_out_impact_pct=remaining_impact_pct,
                leave_one_out_mean_return_advantage_pp=remaining_mean,
                leave_one_out_median_return_advantage_pp=remaining_median,
                removal_flips_result=(
                    mean_return_advantage is not None
                    and remaining_mean is not None
                    and _sign(mean_return_advantage) != 0
                    and _sign(remaining_mean) != 0
                    and _sign(mean_return_advantage) != _sign(remaining_mean)
                ),
            )
        )

    contribution_shares = sorted(
        (
            row.absolute_contribution_share_pct
            for row in enriched
            if row.absolute_contribution_share_pct is not None
        ),
        reverse=True,
    )
    top_share = contribution_shares[0] if contribution_shares else None
    top_three = sum(contribution_shares[:3], start=_ZERO) if contribution_shares else None
    hhi = (
        sum(((share / _HUNDRED) ** 2 for share in contribution_shares), start=_ZERO)
        if contribution_shares
        else None
    )
    any_flip = any(row.removal_flips_result for row in enriched)
    conclusion_basis = mean_return_advantage or _ZERO
    conclusion, conclusion_text = _conclusion(conclusion_basis, top_share, any_flip)
    positive = sum(1 for value in return_advantages if value > _TIE_EPSILON_PP)
    negative = sum(1 for value in return_advantages if value < -_TIE_EPSILON_PP)
    tie = len(return_advantages) - positive - negative
    no_trigger = sum(1 for row in enriched if row.status == "NO_TRIGGER")
    excluded = len(enriched) - len(triggered) - no_trigger

    loo_means = [
        row.leave_one_out_mean_return_advantage_pp
        for row in enriched
        if row.status == "TRIGGERED" and row.leave_one_out_mean_return_advantage_pp is not None
    ]
    loo_min = min(loo_means) if len(loo_means) >= 2 else None
    loo_max = max(loo_means) if len(loo_means) >= 2 else None
    loo_positive_fraction_pct = (
        sum(1 for v in loo_means if v > 0) / Decimal(len(loo_means)) * _HUNDRED
        if len(loo_means) >= 2
        else None
    )

    return ContinuousLossBacktestResult(
        methodology=(
            "Sell on the first trading day after 365 uninterrupted calendar days below "
            "the split-adjusted first INITIATE price. Equal-weight proceeds across every "
            "other holding with measurable start and end prices, then compare both paths "
            "through that stock's actual exit. Every triggered episode receives the same "
            "hypothetical ₹100, so equal-episode mean uplift is the primary result when "
            "future capital allocation is unknown. Median, win/loss/tie rates, leave-one-out "
            "sensitivity, and equal-capital totals assess robustness. Historical rupee and "
            "capital-weighted results are secondary. Holdings without measurable prices are "
            "excluded from that episode's equal-weight basket and reported."
        ),
        closed_episodes=len(episodes),
        triggered_episodes=len(triggered),
        no_trigger_episodes=no_trigger,
        excluded_episodes=excluded,
        trigger_rate_pct=(
            Decimal(len(triggered)) / Decimal(len(episodes)) * _HUNDRED if episodes else _ZERO
        ),
        total_trigger_proceeds=total_proceeds,
        common_end_date=None,
        stock_end_value=stock_end_value,
        diversified_end_value=diversified_end_value,
        net_impact_rupees=net_impact,
        stock_xirr=None,
        diversified_xirr=None,
        annualized_advantage_pp=None,
        terminal_value_uplift_pct=terminal_value_uplift,
        mean_portfolio_impact_pp=None,
        median_portfolio_impact_pp=None,
        largest_portfolio_impact_pp=None,
        equal_capital_start_value=equal_capital_start,
        hold_equal_capital_end_value=hold_equal_capital_end,
        diversified_equal_capital_end_value=diversified_equal_capital_end,
        equal_capital_net_difference=(diversified_equal_capital_end - hold_equal_capital_end),
        mean_return_advantage_pp=mean_return_advantage,
        median_return_advantage_pp=median_return_advantage,
        average_winner_pp=average_winner,
        average_loser_pp=average_loser,
        payoff_ratio=payoff_ratio,
        profit_factor=profit_factor,
        positive_effect_sum_pp=positive_effect_sum,
        negative_effect_sum_pp=negative_effect_sum,
        historical_capital_weighted_uplift_pct=historical_capital_weighted_uplift,
        stock_return_pct=stock_return,
        diversified_return_pct=diversified_return,
        return_uplift_pct=(
            diversified_return - stock_return
            if diversified_return is not None and stock_return is not None
            else None
        ),
        positive_episodes=positive,
        negative_episodes=negative,
        tie_episodes=tie,
        positive_episode_rate_pct=(
            Decimal(positive) / Decimal(len(triggered)) * _HUNDRED if triggered else None
        ),
        tie_episode_rate_pct=(
            Decimal(tie) / Decimal(len(triggered)) * _HUNDRED if triggered else None
        ),
        top_episode_contribution_pct=top_share,
        top_three_contribution_pct=top_three,
        contribution_hhi=hhi,
        conclusion=conclusion,
        conclusion_text=conclusion_text,
        loo_min_mean_return_advantage_pp=loo_min,
        loo_max_mean_return_advantage_pp=loo_max,
        loo_positive_fraction_pct=loo_positive_fraction_pct,
        episodes=tuple(enriched),
    )
