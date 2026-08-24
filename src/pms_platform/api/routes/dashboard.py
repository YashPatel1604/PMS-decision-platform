"""Dashboard summary and exit-insight API routes."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.analytics.episode_performance import first_buy_to_sell_return_pct
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.api.routes.episodes import _exit_outcome, get_db
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import (
    DecisionEvent,
    EpisodePerformance,
    PostExitHorizonPerformance,
    PostExitPerformance,
    Security,
    SellAssessment,
)

router = APIRouter()


class DashboardSummaryResponse(BaseModel):
    """High-level counts for the UI home screen."""

    total_episodes: int
    ownership_ok: int
    ownership_insufficient: int
    post_exit_ok: int
    post_exit_insufficient: int
    assessment_counts: dict[str, int]
    flag_counts: dict[str, int]


class ExitInsightRow(BaseModel):
    episode_id: int
    security_id: str
    portfolio_name: str
    exit_date: str
    comparison_date: str | None
    holding_years: float
    exit_price: float | None
    peak_price: float | None
    peak_price_date: str | None
    ideal_exit_note: str | None
    missed_upside_vs_peak_pct: float | None
    total_return_pct: float | None
    first_buy_to_sell_return_pct: float | None = None
    portfolio_return_pct: float | None
    smallcap_return_pct: float | None
    excess_vs_portfolio: float | None
    stock_annualized_return_pct: float | None
    smallcap_annualized_return_pct: float | None
    excess_vs_smallcap: float | None
    exit_outcome: str
    first_below_cost_date: str | None
    days_held_after_first_loss: int | None
    calendar_days_held_after_first_loss: int | None
    was_profitable_before_loss: bool | None
    loss_hold_pattern: str | None
    security_return_after_exit: float | None
    portfolio_return_after_exit: float | None
    smallcap_return_after_exit: float | None
    excess_vs_portfolio_after_exit: float | None
    excess_vs_smallcap_after_exit: float | None
    current_price: float | None
    current_price_date: str | None
    current_vs_exit_pct: float | None
    exit_assessment: str
    assessment_flags: list[str]
    ownership_signals: list[str]
    post_exit_signals: list[str]
    assessment_confidence: str | None
    post_exit_horizons: list[dict[str, str | int | float | None]]
    portfolio_comparator_status: str = "PROVISIONAL"
    assessment_reason: str
    post_exit_summary: str | None = None


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _post_exit_summary(
    stock: Decimal | None,
    portfolio: Decimal | None,
    benchmark: Decimal | None,
) -> str | None:
    parts: list[str] = []
    if stock is not None:
        parts.append(f"stock {stock:+.1f}%")
    if portfolio is not None:
        parts.append(f"portfolio {portfolio:+.1f}%")
    if benchmark is not None:
        parts.append(f"BSE SmallCap {benchmark:+.1f}%")
    if not parts:
        return None
    return "After exit: " + ", ".join(parts)


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(session: Session = Depends(get_db)) -> DashboardSummaryResponse:
    """Return aggregate episode analytics counts."""
    total = session.scalar(select(func.count()).select_from(EpisodePerformance)) or 0
    ownership_ok = session.scalar(
        select(func.count())
        .select_from(EpisodePerformance)
        .where(EpisodePerformance.data_quality_status == "OK")
    ) or 0
    ownership_insufficient = total - ownership_ok

    post_exit_total = session.scalar(select(func.count()).select_from(PostExitPerformance)) or 0
    post_exit_ok = session.scalar(
        select(func.count())
        .select_from(PostExitPerformance)
        .where(PostExitPerformance.data_quality_status == "OK")
    ) or 0
    post_exit_insufficient = post_exit_total - post_exit_ok

    assessments = session.scalars(select(SellAssessment)).all()
    assessment_counts = dict(Counter(row.exit_assessment for row in assessments))
    flag_counter: Counter[str] = Counter()
    for row in assessments:
        if row.assessment_flags:
            for flag in row.assessment_flags.split(","):
                if flag:
                    flag_counter[flag] += 1

    return DashboardSummaryResponse(
        total_episodes=total,
        ownership_ok=ownership_ok,
        ownership_insufficient=ownership_insufficient,
        post_exit_ok=post_exit_ok,
        post_exit_insufficient=post_exit_insufficient,
        assessment_counts=assessment_counts,
        flag_counts=dict(flag_counter),
    )


@router.get("/exit-insights", response_model=list[ExitInsightRow])
def list_exit_insights(session: Session = Depends(get_db)) -> list[ExitInsightRow]:
    """Return sold-stock insights with today's price and ideal-exit context."""
    securities = {row.security_id: row for row in session.scalars(select(Security)).all()}
    assessments = {
        row.episode_id: row for row in session.scalars(select(SellAssessment)).all()
    }
    post_exit_by_episode = {
        row.episode_id: row for row in session.scalars(select(PostExitPerformance)).all()
    }
    horizons_by_episode: dict[int, list[PostExitHorizonPerformance]] = {}
    for horizon in session.scalars(
        select(PostExitHorizonPerformance).order_by(
            PostExitHorizonPerformance.episode_id,
            PostExitHorizonPerformance.post_exit_horizon_performance_id,
        )
    ).all():
        horizons_by_episode.setdefault(horizon.episode_id, []).append(horizon)
    performances = session.scalars(
        select(EpisodePerformance).order_by(EpisodePerformance.exit_date.desc())
    ).all()

    events_by_episode: dict[int, list[DecisionEvent]] = defaultdict(list)
    episode_ids = [perf.episode_id for perf in performances]
    if episode_ids:
        for event in session.scalars(
            select(DecisionEvent)
            .where(DecisionEvent.episode_id.in_(episode_ids))
            .order_by(DecisionEvent.event_date, DecisionEvent.decision_event_id)
        ).all():
            events_by_episode[event.episode_id].append(event)

    rows: list[ExitInsightRow] = []
    for perf in performances:
        security = securities.get(perf.security_id)
        assessment = assessments.get(perf.episode_id)
        post_exit = post_exit_by_episode.get(perf.episode_id)
        price_security_id = resolve_price_security_id(session, perf.security_id, perf.exit_date)
        current = lookup_daily_price(session, price_security_id, date.today())
        current_price = current.adjusted_close if current else None
        exit_price = perf.exit_adjusted_close
        current_vs_exit = None
        if current_price is not None and exit_price is not None and exit_price > 0:
            current_vs_exit = float(
                ((current_price / exit_price) - Decimal("1")) * Decimal("100")
            )

        ideal_note = None
        if perf.peak_price_during_hold is not None and perf.peak_price_date is not None:
            ideal_note = (
                f"Ideal exit near ₹{perf.peak_price_during_hold:,.2f} on "
                f"{perf.peak_price_date.isoformat()}"
            )

        flags = (
            assessment.assessment_flags.split(",")
            if assessment and assessment.assessment_flags
            else []
        )
        buy_to_sell = first_buy_to_sell_return_pct(
            events_by_episode.get(perf.episode_id, [])
        )
        rows.append(
            ExitInsightRow(
                episode_id=perf.episode_id,
                security_id=perf.security_id,
                portfolio_name=security.portfolio_name if security else perf.security_id,
                exit_date=perf.exit_date.isoformat(),
                comparison_date=(
                    post_exit.comparison_date.isoformat()
                    if post_exit and post_exit.comparison_date
                    else None
                ),
                holding_years=round(perf.holding_days / 365.25, 2),
                exit_price=_float(exit_price),
                peak_price=_float(perf.peak_price_during_hold),
                peak_price_date=(
                    perf.peak_price_date.isoformat() if perf.peak_price_date else None
                ),
                ideal_exit_note=ideal_note,
                missed_upside_vs_peak_pct=_float(perf.missed_upside_vs_peak_pct),
                total_return_pct=_float(perf.total_return_pct),
                first_buy_to_sell_return_pct=_float(buy_to_sell),
                portfolio_return_pct=_float(perf.portfolio_return_pct),
                smallcap_return_pct=_float(perf.smallcap_return_pct),
                excess_vs_portfolio=_float(perf.excess_vs_portfolio),
                stock_annualized_return_pct=_float(perf.stock_annualized_return_pct),
                smallcap_annualized_return_pct=_float(perf.smallcap_annualized_return),
                excess_vs_smallcap=_float(perf.excess_vs_smallcap),
                exit_outcome=_exit_outcome(float(perf.total_profit_loss)),
                first_below_cost_date=(
                    perf.first_below_cost_date.isoformat() if perf.first_below_cost_date else None
                ),
                days_held_after_first_loss=perf.days_held_after_first_loss,
                calendar_days_held_after_first_loss=perf.calendar_days_held_after_first_loss,
                was_profitable_before_loss=perf.was_profitable_before_loss,
                loss_hold_pattern=perf.loss_hold_pattern,
                security_return_after_exit=_float(
                    post_exit.security_return_after_exit if post_exit else None
                ),
                portfolio_return_after_exit=_float(
                    post_exit.portfolio_return_after_exit if post_exit else None
                ),
                smallcap_return_after_exit=_float(
                    post_exit.smallcap_return_after_exit if post_exit else None
                ),
                excess_vs_portfolio_after_exit=_float(
                    post_exit.excess_vs_portfolio_after_exit if post_exit else None
                ),
                excess_vs_smallcap_after_exit=_float(
                    post_exit.excess_vs_smallcap_after_exit if post_exit else None
                ),
                current_price=_float(current_price),
                current_price_date=current.trade_date.isoformat() if current else None,
                current_vs_exit_pct=current_vs_exit,
                exit_assessment=assessment.exit_assessment if assessment else "UNKNOWN",
                assessment_flags=flags,
                ownership_signals=(
                    [
                        flag
                        for flag in (assessment.ownership_flags or "").split(",")
                        if flag
                    ]
                    if assessment
                    else []
                ),
                post_exit_signals=(
                    [
                        flag
                        for flag in (assessment.post_exit_flags or "").split(",")
                        if flag
                    ]
                    if assessment
                    else []
                ),
                assessment_confidence=(
                    assessment.assessment_confidence if assessment else None
                ),
                post_exit_horizons=[
                    {
                        "horizon": horizon.horizon,
                        "target_date": (
                            horizon.target_date.isoformat()
                            if horizon.target_date
                            else None
                        ),
                        "comparison_date": (
                            horizon.comparison_date.isoformat()
                            if horizon.comparison_date
                            else None
                        ),
                        "security_return_pct": _float(
                            horizon.security_return_after_exit
                        ),
                        "smallcap_return_pct": _float(
                            horizon.smallcap_return_after_exit
                        ),
                        "excess_vs_smallcap_pct": _float(
                            horizon.excess_vs_smallcap_after_exit
                        ),
                        "provisional_portfolio_return_pct": _float(
                            horizon.provisional_portfolio_return_after_exit
                        ),
                        "data_quality_status": horizon.data_quality_status,
                    }
                    for horizon in horizons_by_episode.get(perf.episode_id, [])
                ],
                assessment_reason=assessment.assessment_reason if assessment else "",
                post_exit_summary=_post_exit_summary(
                    post_exit.security_return_after_exit if post_exit else None,
                    post_exit.portfolio_return_after_exit if post_exit else None,
                    post_exit.smallcap_return_after_exit if post_exit else None,
                ),
            )
        )
    return rows
