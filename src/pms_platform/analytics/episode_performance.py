"""Episode ownership-period performance calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.analytics.benchmark import (
    compute_benchmark_period_return,
    primary_benchmark_code,
)
from pms_platform.analytics.cash_flows import build_episode_cash_flows
from pms_platform.analytics.exit_assessment import annualized_return_pct
from pms_platform.analytics.ownership_metrics import compute_ownership_metrics
from pms_platform.analytics.portfolio_value import compute_portfolio_period_return
from pms_platform.analytics.xirr import compute_xirr
from pms_platform.models import (
    DecisionEvent,
    EpisodeCashFlowRecord,
    EpisodePerformance,
    InvestmentEpisode,
)
from pms_platform.models.enums import EpisodeStatus

CALCULATION_VERSION = "m4-v10"
_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")


@dataclass(frozen=True)
class EpisodeAnalysisSummary:
    """Aggregate outcome of a closed-episode analysis run."""

    analyzed: int
    insufficient: int
    cash_flow_rows: int


def _holding_days(entry_date: date, exit_date: date) -> int:
    return max((exit_date - entry_date).days, 0)


def _average_trade_prices(
    events: list[DecisionEvent],
) -> tuple[Decimal | None, Decimal | None]:
    """Return VWAP buy and sell prices from decision-event trade prices."""
    buy_value = _ZERO
    buy_qty = _ZERO
    sell_value = _ZERO
    sell_qty = _ZERO

    for event in events:
        if event.price is None or event.price <= 0:
            continue
        qty = abs(Decimal(event.quantity_change))
        if qty <= 0:
            continue
        if event.decision_type in {"INITIATE", "ADD"}:
            buy_value += event.price * qty
            buy_qty += qty
        elif event.decision_type in {"REDUCE", "EXIT"}:
            sell_value += event.price * qty
            sell_qty += qty

    avg_buy = buy_value / buy_qty if buy_qty > 0 else None
    avg_sell = sell_value / sell_qty if sell_qty > 0 else None
    return avg_buy, avg_sell


def _first_buy_price(events: list[DecisionEvent]) -> Decimal | None:
    """Earliest INITIATE/ADD trade price."""
    first: DecisionEvent | None = None
    for event in events:
        if event.decision_type not in {"INITIATE", "ADD"}:
            continue
        if event.price is None or event.price <= 0:
            continue
        if abs(int(event.quantity_change or 0)) <= 0:
            continue
        if first is None or (event.event_date, event.decision_event_id or 0) < (
            first.event_date,
            first.decision_event_id or 0,
        ):
            first = event
    return first.price if first is not None else None


def _last_sell_price(events: list[DecisionEvent]) -> Decimal | None:
    """Latest REDUCE/EXIT trade price."""
    last: DecisionEvent | None = None
    for event in events:
        if event.decision_type not in {"REDUCE", "EXIT"}:
            continue
        if event.price is None or event.price <= 0:
            continue
        if abs(int(event.quantity_change or 0)) <= 0:
            continue
        if last is None or (event.event_date, event.decision_event_id or 0) > (
            last.event_date,
            last.decision_event_id or 0,
        ):
            last = event
    return last.price if last is not None else None


@dataclass(frozen=True)
class FirstBuySellMarks:
    first_buy_price: Decimal | None
    last_sell_price: Decimal | None
    avg_sell_price: Decimal | None
    sell_mark_price: Decimal | None
    first_buy_to_sell_return_pct: Decimal | None


def first_buy_sell_marks(events: list[DecisionEvent]) -> FirstBuySellMarks:
    """First buy, avg/last sell, and return using sell mark (last if last > avg)."""
    first_buy = _first_buy_price(events)
    _avg_buy, avg_sell = _average_trade_prices(events)
    last_sell = _last_sell_price(events)
    if first_buy is None or first_buy <= 0 or avg_sell is None:
        return FirstBuySellMarks(
            first_buy_price=first_buy,
            last_sell_price=last_sell,
            avg_sell_price=avg_sell,
            sell_mark_price=None,
            first_buy_to_sell_return_pct=None,
        )
    mark = last_sell if last_sell is not None and last_sell > avg_sell else avg_sell
    return FirstBuySellMarks(
        first_buy_price=first_buy,
        last_sell_price=last_sell,
        avg_sell_price=avg_sell,
        sell_mark_price=mark,
        first_buy_to_sell_return_pct=((mark / first_buy) - _ONE) * _HUNDRED,
    )


def first_buy_to_sell_return_pct(
    events: list[DecisionEvent],
) -> Decimal | None:
    """Return from first buy to sell mark (last sell if last > avg, else avg)."""
    return first_buy_sell_marks(events).first_buy_to_sell_return_pct


def _summarize_cash_flows(flows: list) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    invested = _ZERO
    proceeds = _ZERO
    dividends = _ZERO
    for flow in flows:
        if flow.amount < 0:
            invested += -flow.amount
        elif flow.flow_type == "DIVIDEND":
            dividends += flow.amount
        else:
            proceeds += flow.amount
    profit_loss = invested.copy_negate() + proceeds + dividends
    return invested, proceeds, dividends, profit_loss


def _total_return_pct(profit_loss: Decimal, invested: Decimal) -> Decimal | None:
    if invested <= 0:
        return None
    return (profit_loss / invested) * _HUNDRED


def analyze_closed_episodes(session: Session) -> EpisodeAnalysisSummary:
    """Compute and persist ownership-period metrics for all closed episodes."""
    session.execute(delete(EpisodeCashFlowRecord))
    session.execute(delete(EpisodePerformance))
    session.flush()

    episodes = session.scalars(
        select(InvestmentEpisode)
        .where(InvestmentEpisode.status == EpisodeStatus.CLOSED.value)
        .order_by(InvestmentEpisode.security_id, InvestmentEpisode.episode_number)
    ).all()

    analyzed = 0
    insufficient = 0
    cash_flow_rows = 0
    benchmark_code = primary_benchmark_code()

    for episode in episodes:
        if episode.exit_date is None:
            insufficient += 1
            continue

        events = list(
            session.scalars(
                select(DecisionEvent)
                .where(DecisionEvent.episode_id == episode.episode_id)
                .order_by(DecisionEvent.event_date, DecisionEvent.decision_event_id)
            ).all()
        )
        flows, notes = build_episode_cash_flows(session, episode, events)
        for flow in flows:
            session.add(
                EpisodeCashFlowRecord(
                    episode_id=flow.episode_id,
                    flow_date=flow.flow_date,
                    amount=flow.amount,
                    flow_type=flow.flow_type,
                    source=flow.source,
                    source_reference=flow.source_reference,
                    calculation_version=CALCULATION_VERSION,
                )
            )
        cash_flow_rows += len(flows)

        invested, proceeds, dividends, profit_loss = _summarize_cash_flows(flows)
        average_buy_price, average_sell_price = _average_trade_prices(events)
        cash_flow_pairs = [(flow.flow_date, flow.amount) for flow in flows]
        stock_xirr = compute_xirr(cash_flow_pairs)
        total_return_pct = _total_return_pct(profit_loss, invested)
        holding_days = _holding_days(episode.entry_date, episode.exit_date)

        benchmark = compute_benchmark_period_return(
            session,
            benchmark_code=benchmark_code,
            start_date=episode.entry_date,
            end_date=episode.exit_date,
        )
        portfolio = compute_portfolio_period_return(
            session,
            start_date=episode.entry_date,
            end_date=episode.exit_date,
        )
        ownership = compute_ownership_metrics(
            session,
            security_id=episode.security_id,
            entry_date=episode.entry_date,
            exit_date=episode.exit_date,
            events=events,
            benchmark_code=benchmark_code,
            sold_at_loss=profit_loss < _ZERO,
        )
        all_notes = [*notes, *ownership.notes]

        stock_annualized = (
            annualized_return_pct(total_return_pct, holding_days)
            if total_return_pct is not None
            else None
        )

        status = "OK"
        if notes or stock_xirr is None or benchmark is None:
            status = "INSUFFICIENT"
            insufficient += 1
        else:
            analyzed += 1

        excess_vs_smallcap = None
        if total_return_pct is not None and benchmark is not None:
            excess_vs_smallcap = total_return_pct - benchmark.total_return_pct

        excess_vs_portfolio = None
        if total_return_pct is not None and portfolio is not None:
            excess_vs_portfolio = total_return_pct - portfolio.total_return_pct

        session.add(
            EpisodePerformance(
                episode_id=episode.episode_id,
                security_id=episode.security_id,
                entry_date=episode.entry_date,
                exit_date=episode.exit_date,
                holding_days=holding_days,
                total_invested=invested,
                total_sale_proceeds=proceeds,
                dividends_received=dividends,
                total_profit_loss=profit_loss,
                average_buy_price=average_buy_price,
                average_sell_price=average_sell_price,
                total_return_pct=total_return_pct,
                stock_xirr=stock_xirr,
                portfolio_return_pct=portfolio.total_return_pct if portfolio else None,
                portfolio_annualized_return=(
                    portfolio.annualized_return_pct if portfolio else None
                ),
                excess_vs_portfolio=excess_vs_portfolio,
                smallcap_return_pct=benchmark.total_return_pct if benchmark else None,
                smallcap_annualized_return=benchmark.annualized_return_pct if benchmark else None,
                excess_vs_smallcap=excess_vs_smallcap,
                max_drawdown=ownership.max_drawdown_pct,
                max_unrealized_gain=ownership.max_unrealized_gain_pct,
                days_below_cost=ownership.days_below_cost,
                days_underperforming_benchmark=ownership.days_underperforming_benchmark,
                first_below_cost_date=ownership.first_below_cost_date,
                days_held_after_first_loss=ownership.days_held_after_first_loss,
                calendar_days_held_after_first_loss=ownership.calendar_days_held_after_first_loss,
                was_profitable_before_loss=ownership.was_profitable_before_loss,
                loss_hold_pattern=ownership.loss_hold_pattern,
                peak_price_during_hold=ownership.peak_price,
                peak_price_date=ownership.peak_price_date,
                exit_adjusted_close=ownership.exit_adjusted_close,
                missed_upside_vs_peak_pct=ownership.missed_upside_vs_peak_pct,
                stock_annualized_return_pct=stock_annualized,
                ownership_trading_days=ownership.ownership_trading_days,
                benchmark_code=benchmark_code if benchmark else None,
                benchmark_start_level=benchmark.start_level if benchmark else None,
                benchmark_end_level=benchmark.end_level if benchmark else None,
                calculation_version=CALCULATION_VERSION,
                data_quality_status=status,
                data_quality_notes="; ".join(all_notes) if all_notes else None,
            )
        )

    session.flush()
    return EpisodeAnalysisSummary(
        analyzed=analyzed,
        insufficient=insufficient,
        cash_flow_rows=cash_flow_rows,
    )
