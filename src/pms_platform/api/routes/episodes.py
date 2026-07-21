"""Episode analytics API routes."""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.benchmark import (
    compute_benchmark_period_return,
    primary_benchmark_code,
)
from pms_platform.analytics.portfolio_value import compute_portfolio_period_return
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.db.base import get_session_factory
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import (
    DailyPrice,
    EpisodePerformance,
    PostExitHorizonPerformance,
    PostExitPerformance,
    Security,
    SellAssessment,
)
from pms_platform.portfolio.position_engine import compute_quantities_as_of

router = APIRouter()


def _exit_outcome(profit_loss: float) -> str:
    if profit_loss > 0:
        return "PROFIT_STOCK"
    if profit_loss < 0:
        return "LOSS_STOCK"
    return "BREAKEVEN"


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for API handlers."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


class EqualWeightReinvestmentResponse(BaseModel):
    start_date: str
    end_date: str
    stock_return_pct: float | None
    equal_weight_other_holdings_return_pct: float | None
    reinvestment_advantage_pct: float | None
    value_if_stock_100: float | None
    value_if_reinvested_100: float | None
    included_holdings: int
    excluded_missing_prices: int
    methodology: str


class MajorLossWindowResponse(BaseModel):
    start_date: str
    end_date: str
    calendar_days: int
    trading_days: int | None
    pattern: str
    start_price: float | None
    end_price: float | None
    stock_return_pct: float | None
    portfolio_return_pct: float | None
    smallcap_return_pct: float | None
    stock_vs_portfolio_pct: float | None
    stock_vs_smallcap_pct: float | None
    portfolio_vs_smallcap_pct: float | None
    portfolio_methodology: str | None
    reinvestment_after_loss: EqualWeightReinvestmentResponse | None
    reinvestment_at_one_year_loss: EqualWeightReinvestmentResponse | None


class PostExitHorizonResponse(BaseModel):
    horizon: str
    target_date: str | None
    comparison_date: str | None
    days_after_exit: int | None
    security_return_pct: float | None
    smallcap_return_pct: float | None
    excess_vs_smallcap_pct: float | None
    provisional_portfolio_return_pct: float | None
    provisional_excess_vs_portfolio_pct: float | None
    data_quality_status: str


class EpisodePerformanceResponse(BaseModel):
    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: str
    exit_date: str
    holding_days: int
    total_invested: float
    total_profit_loss: float
    exit_outcome: str
    average_buy_price: float | None
    average_sell_price: float | None
    total_return_pct: float | None
    stock_xirr: float | None
    portfolio_return_pct: float | None
    smallcap_return_pct: float | None
    excess_vs_smallcap: float | None
    excess_vs_portfolio: float | None
    max_drawdown: float | None
    peak_price_during_hold: float | None
    peak_price_date: str | None
    exit_adjusted_close: float | None
    missed_upside_vs_peak_pct: float | None
    days_below_cost: int | None
    days_underperforming_benchmark: int | None
    first_below_cost_date: str | None
    days_held_after_first_loss: int | None
    calendar_days_held_after_first_loss: int | None
    was_profitable_before_loss: bool | None
    loss_hold_pattern: str | None
    comparison_date: str | None
    security_return_after_exit: float | None
    portfolio_return_after_exit: float | None
    smallcap_return_after_exit: float | None
    excess_vs_smallcap_after_exit: float | None
    excess_vs_portfolio_after_exit: float | None
    major_loss_window: MajorLossWindowResponse | None = None
    exit_assessment: str | None
    ownership_signals: list[str]
    post_exit_signals: list[str]
    assessment_confidence: str | None
    assessment_evidence: dict[str, str | int | float | None]
    post_exit_horizons: list[PostExitHorizonResponse]
    portfolio_comparator_status: str = "PROVISIONAL"
    assessment_reason: str | None
    data_quality_status: str


class PostExitResponse(BaseModel):
    episode_id: int
    exit_date: str
    comparison_date: str | None
    security_return_after_exit: float | None
    portfolio_return_after_exit: float | None
    smallcap_return_after_exit: float | None
    excess_vs_smallcap_after_exit: float | None
    exit_assessment: str | None
    assessment_reason: str | None
    data_quality_status: str


class AnalysisRunResponse(BaseModel):
    ownership_ok: int
    ownership_insufficient: int
    post_exit_ok: int
    post_exit_insufficient: int
    cash_flow_rows: int


def _performance_response(
    row: EpisodePerformance,
    portfolio_name: str,
    assessment: SellAssessment | None,
    post_exit: PostExitPerformance | None = None,
    horizons: list[PostExitHorizonPerformance] | None = None,
    major_loss_window: MajorLossWindowResponse | None = None,
) -> EpisodePerformanceResponse:
    profit_loss = float(row.total_profit_loss)
    stock_after = (
        float(post_exit.security_return_after_exit)
        if post_exit and post_exit.security_return_after_exit is not None
        else None
    )
    portfolio_after = (
        float(post_exit.portfolio_return_after_exit)
        if post_exit and post_exit.portfolio_return_after_exit is not None
        else None
    )
    smallcap_after = (
        float(post_exit.smallcap_return_after_exit)
        if post_exit and post_exit.smallcap_return_after_exit is not None
        else None
    )
    return EpisodePerformanceResponse(
        episode_id=row.episode_id,
        security_id=row.security_id,
        portfolio_name=portfolio_name,
        entry_date=row.entry_date.isoformat(),
        exit_date=row.exit_date.isoformat(),
        holding_days=row.holding_days,
        total_invested=float(row.total_invested),
        total_profit_loss=profit_loss,
        exit_outcome=_exit_outcome(profit_loss),
        average_buy_price=(
            float(row.average_buy_price) if row.average_buy_price is not None else None
        ),
        average_sell_price=(
            float(row.average_sell_price) if row.average_sell_price is not None else None
        ),
        total_return_pct=float(row.total_return_pct) if row.total_return_pct else None,
        stock_xirr=float(row.stock_xirr) if row.stock_xirr else None,
        portfolio_return_pct=float(row.portfolio_return_pct) if row.portfolio_return_pct else None,
        smallcap_return_pct=float(row.smallcap_return_pct) if row.smallcap_return_pct else None,
        excess_vs_smallcap=float(row.excess_vs_smallcap) if row.excess_vs_smallcap else None,
        excess_vs_portfolio=float(row.excess_vs_portfolio) if row.excess_vs_portfolio else None,
        max_drawdown=float(row.max_drawdown) if row.max_drawdown else None,
        peak_price_during_hold=(
            float(row.peak_price_during_hold) if row.peak_price_during_hold is not None else None
        ),
        peak_price_date=row.peak_price_date.isoformat() if row.peak_price_date else None,
        exit_adjusted_close=(
            float(row.exit_adjusted_close) if row.exit_adjusted_close is not None else None
        ),
        missed_upside_vs_peak_pct=(
            float(row.missed_upside_vs_peak_pct)
            if row.missed_upside_vs_peak_pct is not None
            else None
        ),
        days_below_cost=row.days_below_cost,
        days_underperforming_benchmark=row.days_underperforming_benchmark,
        first_below_cost_date=(
            row.first_below_cost_date.isoformat() if row.first_below_cost_date else None
        ),
        days_held_after_first_loss=row.days_held_after_first_loss,
        calendar_days_held_after_first_loss=row.calendar_days_held_after_first_loss,
        was_profitable_before_loss=row.was_profitable_before_loss,
        loss_hold_pattern=row.loss_hold_pattern,
        comparison_date=(
            post_exit.comparison_date.isoformat()
            if post_exit and post_exit.comparison_date
            else None
        ),
        security_return_after_exit=stock_after,
        portfolio_return_after_exit=portfolio_after,
        smallcap_return_after_exit=smallcap_after,
        excess_vs_smallcap_after_exit=(
            float(post_exit.excess_vs_smallcap_after_exit)
            if post_exit and post_exit.excess_vs_smallcap_after_exit is not None
            else None
        ),
        excess_vs_portfolio_after_exit=(
            stock_after - portfolio_after
            if stock_after is not None and portfolio_after is not None
            else None
        ),
        major_loss_window=major_loss_window,
        exit_assessment=assessment.exit_assessment if assessment else None,
        ownership_signals=(
            [flag for flag in (assessment.ownership_flags or "").split(",") if flag]
            if assessment
            else []
        ),
        post_exit_signals=(
            [flag for flag in (assessment.post_exit_flags or "").split(",") if flag]
            if assessment
            else []
        ),
        assessment_confidence=(
            assessment.assessment_confidence if assessment else None
        ),
        assessment_evidence=(
            json.loads(assessment.assessment_evidence)
            if assessment and assessment.assessment_evidence
            else {}
        ),
        post_exit_horizons=[
            PostExitHorizonResponse(
                horizon=horizon.horizon,
                target_date=(
                    horizon.target_date.isoformat() if horizon.target_date else None
                ),
                comparison_date=(
                    horizon.comparison_date.isoformat()
                    if horizon.comparison_date
                    else None
                ),
                days_after_exit=horizon.days_after_exit,
                security_return_pct=(
                    float(horizon.security_return_after_exit)
                    if horizon.security_return_after_exit is not None
                    else None
                ),
                smallcap_return_pct=(
                    float(horizon.smallcap_return_after_exit)
                    if horizon.smallcap_return_after_exit is not None
                    else None
                ),
                excess_vs_smallcap_pct=(
                    float(horizon.excess_vs_smallcap_after_exit)
                    if horizon.excess_vs_smallcap_after_exit is not None
                    else None
                ),
                provisional_portfolio_return_pct=(
                    float(horizon.provisional_portfolio_return_after_exit)
                    if horizon.provisional_portfolio_return_after_exit is not None
                    else None
                ),
                provisional_excess_vs_portfolio_pct=(
                    float(horizon.provisional_excess_vs_portfolio_after_exit)
                    if horizon.provisional_excess_vs_portfolio_after_exit
                    is not None
                    else None
                ),
                data_quality_status=horizon.data_quality_status,
            )
            for horizon in (horizons or [])
        ],
        assessment_reason=assessment.assessment_reason if assessment else None,
        data_quality_status=row.data_quality_status,
    )


def _equal_weight_reinvestment(
    session: Session,
    row: EpisodePerformance,
    start: date,
    methodology: str,
) -> EqualWeightReinvestmentResponse | None:
    """Compare holding the stock with an equal-weight switch into other holdings."""
    end = row.exit_date
    if start >= end:
        return None

    stock_start_security_id = resolve_price_security_id(session, row.security_id, start)
    stock_end_security_id = resolve_price_security_id(session, row.security_id, end)
    stock_start = lookup_daily_price(session, stock_start_security_id, start)
    stock_end = lookup_daily_price(session, stock_end_security_id, end)
    stock_return: Decimal | None = None
    if stock_start is not None and stock_end is not None and stock_start.adjusted_close > 0:
        stock_return = (
            (stock_end.adjusted_close / stock_start.adjusted_close) - Decimal("1")
        ) * Decimal("100")

    quantities = compute_quantities_as_of(session, start)
    constituent_returns: list[Decimal] = []
    excluded_missing_prices = 0
    for security_id, quantity in quantities.items():
        if security_id == row.security_id or quantity <= 0:
            continue
        start_security_id = resolve_price_security_id(session, security_id, start)
        end_security_id = resolve_price_security_id(session, security_id, end)
        start_price = lookup_daily_price(session, start_security_id, start)
        end_price = lookup_daily_price(session, end_security_id, end)
        if start_price is None or end_price is None or start_price.adjusted_close <= 0:
            excluded_missing_prices += 1
            continue
        constituent_returns.append(
            ((end_price.adjusted_close / start_price.adjusted_close) - Decimal("1"))
            * Decimal("100")
        )

    equal_weight_return = (
        sum(constituent_returns, start=Decimal("0")) / Decimal(len(constituent_returns))
        if constituent_returns
        else None
    )
    advantage = (
        equal_weight_return - stock_return
        if equal_weight_return is not None and stock_return is not None
        else None
    )

    return EqualWeightReinvestmentResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        stock_return_pct=float(stock_return) if stock_return is not None else None,
        equal_weight_other_holdings_return_pct=(
            float(equal_weight_return) if equal_weight_return is not None else None
        ),
        reinvestment_advantage_pct=float(advantage) if advantage is not None else None,
        value_if_stock_100=(
            float(Decimal("100") * (Decimal("1") + stock_return / Decimal("100")))
            if stock_return is not None
            else None
        ),
        value_if_reinvested_100=(
            float(Decimal("100") * (Decimal("1") + equal_weight_return / Decimal("100")))
            if equal_weight_return is not None
            else None
        ),
        included_holdings=len(constituent_returns),
        excluded_missing_prices=excluded_missing_prices,
        methodology=methodology,
    )


def _one_year_loss_trigger_date(
    session: Session,
    row: EpisodePerformance,
    loss_start: date,
) -> date | None:
    """Return the first trading date on/after 365 continuous calendar loss days."""
    anniversary = loss_start + timedelta(days=365)
    price_security_id = resolve_price_security_id(session, row.security_id, anniversary)
    return session.scalar(
        select(DailyPrice.trade_date)
        .where(
            DailyPrice.security_id == price_security_id,
            DailyPrice.trade_date >= anniversary,
            DailyPrice.trade_date <= row.exit_date,
        )
        .order_by(DailyPrice.trade_date)
        .limit(1)
    )


def _major_loss_window(
    session: Session,
    row: EpisodePerformance,
) -> MajorLossWindowResponse | None:
    """Compare stock, portfolio, and BSE SmallCap over a 1y+ loss window."""
    start = row.first_below_cost_date
    calendar_days = row.calendar_days_held_after_first_loss
    if start is None or calendar_days is None or calendar_days < 365:
        return None

    end = start + timedelta(days=calendar_days)
    start_price = lookup_daily_price(session, row.security_id, start)
    end_price = lookup_daily_price(session, row.security_id, end)
    stock_return: Decimal | None = None
    if start_price is not None and end_price is not None and start_price.adjusted_close > 0:
        stock_return = (
            (end_price.adjusted_close / start_price.adjusted_close) - Decimal("1")
        ) * Decimal("100")

    portfolio = compute_portfolio_period_return(
        session,
        start_date=start,
        end_date=end,
    )
    benchmark = compute_benchmark_period_return(
        session,
        benchmark_code=primary_benchmark_code(),
        start_date=start,
        end_date=end,
    )
    portfolio_return = portfolio.total_return_pct if portfolio else None
    smallcap_return = benchmark.total_return_pct if benchmark else None

    def difference(left: Decimal | None, right: Decimal | None) -> float | None:
        return float(left - right) if left is not None and right is not None else None

    one_year_trigger = _one_year_loss_trigger_date(session, row, start)
    return MajorLossWindowResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        calendar_days=calendar_days,
        trading_days=row.days_held_after_first_loss,
        pattern=row.loss_hold_pattern or "LONG_CONTINUOUS_LOSS",
        start_price=float(start_price.adjusted_close) if start_price else None,
        end_price=float(end_price.adjusted_close) if end_price else None,
        stock_return_pct=float(stock_return) if stock_return is not None else None,
        portfolio_return_pct=float(portfolio_return) if portfolio_return is not None else None,
        smallcap_return_pct=float(smallcap_return) if smallcap_return is not None else None,
        stock_vs_portfolio_pct=difference(stock_return, portfolio_return),
        stock_vs_smallcap_pct=difference(stock_return, smallcap_return),
        portfolio_vs_smallcap_pct=difference(portfolio_return, smallcap_return),
        portfolio_methodology=portfolio.methodology if portfolio else None,
        reinvestment_after_loss=_equal_weight_reinvestment(
            session,
            row,
            end,
            "EQUAL_WEIGHT_OTHER_EQUITIES_AT_LOSS_WINDOW_END",
        ),
        reinvestment_at_one_year_loss=(
            _equal_weight_reinvestment(
                session,
                row,
                one_year_trigger,
                "EQUAL_WEIGHT_OTHER_EQUITIES_AT_ONE_YEAR_CONTINUOUS_LOSS",
            )
            if one_year_trigger is not None
            else None
        ),
    )


@router.post("/analyze", response_model=AnalysisRunResponse)
def analyze_episodes(session: Session = Depends(get_db)) -> AnalysisRunResponse:
    """Recompute episode analytics and persist results."""
    from pms_platform.analytics.service import run_full_episode_analysis

    summary = run_full_episode_analysis(session)
    session.commit()
    return AnalysisRunResponse(
        ownership_ok=summary.ownership_ok,
        ownership_insufficient=summary.ownership_insufficient,
        post_exit_ok=summary.post_exit_ok,
        post_exit_insufficient=summary.post_exit_insufficient,
        cash_flow_rows=summary.cash_flow_rows,
    )


@router.get("/performance", response_model=list[EpisodePerformanceResponse])
def list_episode_performance(
    session: Session = Depends(get_db),
) -> list[EpisodePerformanceResponse]:
    """List ownership-period performance rows."""
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
    rows = session.scalars(
        select(EpisodePerformance).order_by(
            EpisodePerformance.exit_date.desc(),
            EpisodePerformance.security_id,
        )
    ).all()
    return [
        _performance_response(
            row,
            securities[row.security_id].portfolio_name
            if row.security_id in securities
            else row.security_id,
            assessments.get(row.episode_id),
            post_exit_by_episode.get(row.episode_id),
            horizons_by_episode.get(row.episode_id),
        )
        for row in rows
    ]


@router.get("/performance/{episode_id}", response_model=EpisodePerformanceResponse)
def get_episode_performance(
    episode_id: int,
    session: Session = Depends(get_db),
) -> EpisodePerformanceResponse:
    """Return ownership-period performance for one episode."""
    row = session.scalar(
        select(EpisodePerformance).where(EpisodePerformance.episode_id == episode_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Episode performance not found")
    security = session.scalar(select(Security).where(Security.security_id == row.security_id))
    assessment = session.scalar(
        select(SellAssessment).where(SellAssessment.episode_id == episode_id)
    )
    post_exit = session.scalar(
        select(PostExitPerformance).where(PostExitPerformance.episode_id == episode_id)
    )
    horizons = session.scalars(
        select(PostExitHorizonPerformance).where(
            PostExitHorizonPerformance.episode_id == episode_id
        )
    ).all()
    return _performance_response(
        row,
        security.portfolio_name if security else row.security_id,
        assessment,
        post_exit,
        list(horizons),
        _major_loss_window(session, row),
    )


@router.get("/post-exit", response_model=list[PostExitResponse])
def list_post_exit_performance(session: Session = Depends(get_db)) -> list[PostExitResponse]:
    """List post-exit performance and sell assessments."""
    post_exit_rows = {
        row.episode_id: row
        for row in session.scalars(select(PostExitPerformance)).all()
    }
    assessments = {
        row.episode_id: row for row in session.scalars(select(SellAssessment)).all()
    }
    payload: list[PostExitResponse] = []
    for episode_id, row in sorted(post_exit_rows.items(), key=lambda item: item[1].exit_date, reverse=True):
        assessment = assessments.get(episode_id)
        payload.append(
            PostExitResponse(
                episode_id=episode_id,
                exit_date=row.exit_date.isoformat(),
                comparison_date=row.comparison_date.isoformat() if row.comparison_date else None,
                security_return_after_exit=float(row.security_return_after_exit)
                if row.security_return_after_exit is not None
                else None,
                portfolio_return_after_exit=float(row.portfolio_return_after_exit)
                if row.portfolio_return_after_exit is not None
                else None,
                smallcap_return_after_exit=float(row.smallcap_return_after_exit)
                if row.smallcap_return_after_exit is not None
                else None,
                excess_vs_smallcap_after_exit=float(row.excess_vs_smallcap_after_exit)
                if row.excess_vs_smallcap_after_exit is not None
                else None,
                exit_assessment=assessment.exit_assessment if assessment else None,
                assessment_reason=assessment.assessment_reason if assessment else None,
                data_quality_status=row.data_quality_status,
            )
        )
    return payload


@router.get("/post-exit/{episode_id}", response_model=PostExitResponse)
def get_post_exit_performance(
    episode_id: int,
    session: Session = Depends(get_db),
) -> PostExitResponse:
    """Return post-exit performance for one episode."""
    row = session.scalar(
        select(PostExitPerformance).where(PostExitPerformance.episode_id == episode_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Post-exit performance not found")
    assessment = session.scalar(
        select(SellAssessment).where(SellAssessment.episode_id == episode_id)
    )
    return PostExitResponse(
        episode_id=episode_id,
        exit_date=row.exit_date.isoformat(),
        comparison_date=row.comparison_date.isoformat() if row.comparison_date else None,
        security_return_after_exit=float(row.security_return_after_exit)
        if row.security_return_after_exit is not None
        else None,
        portfolio_return_after_exit=float(row.portfolio_return_after_exit)
        if row.portfolio_return_after_exit is not None
        else None,
        smallcap_return_after_exit=float(row.smallcap_return_after_exit)
        if row.smallcap_return_after_exit is not None
        else None,
        excess_vs_smallcap_after_exit=float(row.excess_vs_smallcap_after_exit)
        if row.excess_vs_smallcap_after_exit is not None
        else None,
        exit_assessment=assessment.exit_assessment if assessment else None,
        assessment_reason=assessment.assessment_reason if assessment else None,
        data_quality_status=row.data_quality_status,
    )
