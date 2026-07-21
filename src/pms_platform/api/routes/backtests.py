"""Research backtest API routes."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pms_platform.analytics.continuous_loss_backtest import (
    ContinuousLossEpisodeResult,
    run_continuous_loss_backtest,
)
from pms_platform.api.routes.episodes import get_db

router = APIRouter()


class ContinuousLossEpisodeResponse(BaseModel):
    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: str
    exit_date: str
    status: str
    initial_purchase_price: float | None
    adjusted_initial_price_threshold: float | None
    underwater_start_date: str | None
    trigger_date: str | None
    measurement_days: int | None
    trigger_quantity: int | None
    trigger_price: float | None
    trigger_proceeds: float | None
    common_end_date: str | None
    stock_return_pct: float | None
    diversified_return_pct: float | None
    return_uplift_pct: float | None
    stock_cagr_pct: float | None
    diversified_cagr_pct: float | None
    annualized_advantage_pp: float | None
    stock_end_value: float | None
    diversified_end_value: float | None
    impact_rupees: float | None
    impact_pct_of_trigger: float | None
    trigger_portfolio_value: float | None
    trigger_equity_value: float | None
    trigger_liquid_value: float | None
    portfolio_denominator_status: str | None
    position_weight_pct: float | None
    hold_portfolio_contribution_pct: float | None
    diversified_portfolio_contribution_pct: float | None
    portfolio_impact_pp: float | None
    other_holdings_count: int
    priced_holdings_count: int
    missing_price_holdings_count: int
    absolute_contribution_share_pct: float | None
    leave_one_out_impact_rupees: float | None
    leave_one_out_impact_pct: float | None
    leave_one_out_stock_xirr: float | None
    leave_one_out_diversified_xirr: float | None
    leave_one_out_annualized_advantage_pp: float | None
    leave_one_out_mean_portfolio_impact_pp: float | None
    leave_one_out_median_portfolio_impact_pp: float | None
    leave_one_out_mean_return_advantage_pp: float | None
    leave_one_out_median_return_advantage_pp: float | None
    removal_flips_result: bool
    note: str | None


class ContinuousLossBacktestResponse(BaseModel):
    methodology: str
    closed_episodes: int
    triggered_episodes: int
    no_trigger_episodes: int
    excluded_episodes: int
    trigger_rate_pct: float
    total_trigger_proceeds: float
    common_end_date: str | None
    stock_end_value: float
    diversified_end_value: float
    net_impact_rupees: float
    stock_xirr: float | None
    diversified_xirr: float | None
    annualized_advantage_pp: float | None
    terminal_value_uplift_pct: float | None
    mean_portfolio_impact_pp: float | None
    median_portfolio_impact_pp: float | None
    largest_portfolio_impact_pp: float | None
    equal_capital_start_value: float
    hold_equal_capital_end_value: float
    diversified_equal_capital_end_value: float
    equal_capital_net_difference: float
    mean_return_advantage_pp: float | None
    median_return_advantage_pp: float | None
    positive_effect_sum_pp: float
    negative_effect_sum_pp: float
    stock_return_pct: float | None
    diversified_return_pct: float | None
    return_uplift_pct: float | None
    positive_episodes: int
    negative_episodes: int
    positive_episode_rate_pct: float | None
    top_episode_contribution_pct: float | None
    top_three_contribution_pct: float | None
    contribution_hhi: float | None
    conclusion: str
    conclusion_text: str
    episodes: list[ContinuousLossEpisodeResponse]


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _episode_response(row: ContinuousLossEpisodeResult) -> ContinuousLossEpisodeResponse:
    return ContinuousLossEpisodeResponse(
        episode_id=row.episode_id,
        security_id=row.security_id,
        portfolio_name=row.portfolio_name,
        entry_date=row.entry_date.isoformat(),
        exit_date=row.exit_date.isoformat(),
        status=row.status,
        initial_purchase_price=_float(row.initial_purchase_price),
        adjusted_initial_price_threshold=_float(row.adjusted_initial_price_threshold),
        underwater_start_date=(
            row.underwater_start_date.isoformat() if row.underwater_start_date else None
        ),
        trigger_date=row.trigger_date.isoformat() if row.trigger_date else None,
        measurement_days=row.measurement_days,
        trigger_quantity=row.trigger_quantity,
        trigger_price=_float(row.trigger_price),
        trigger_proceeds=_float(row.trigger_proceeds),
        common_end_date=row.common_end_date.isoformat() if row.common_end_date else None,
        stock_return_pct=_float(row.stock_return_pct),
        diversified_return_pct=_float(row.diversified_return_pct),
        return_uplift_pct=_float(row.return_uplift_pct),
        stock_cagr_pct=_float(row.stock_cagr_pct),
        diversified_cagr_pct=_float(row.diversified_cagr_pct),
        annualized_advantage_pp=_float(row.annualized_advantage_pp),
        stock_end_value=_float(row.stock_end_value),
        diversified_end_value=_float(row.diversified_end_value),
        impact_rupees=_float(row.impact_rupees),
        impact_pct_of_trigger=_float(row.impact_pct_of_trigger),
        trigger_portfolio_value=_float(row.trigger_portfolio_value),
        trigger_equity_value=_float(row.trigger_equity_value),
        trigger_liquid_value=_float(row.trigger_liquid_value),
        portfolio_denominator_status=row.portfolio_denominator_status,
        position_weight_pct=_float(row.position_weight_pct),
        hold_portfolio_contribution_pct=_float(row.hold_portfolio_contribution_pct),
        diversified_portfolio_contribution_pct=_float(row.diversified_portfolio_contribution_pct),
        portfolio_impact_pp=_float(row.portfolio_impact_pp),
        other_holdings_count=row.other_holdings_count,
        priced_holdings_count=row.priced_holdings_count,
        missing_price_holdings_count=row.missing_price_holdings_count,
        absolute_contribution_share_pct=_float(row.absolute_contribution_share_pct),
        leave_one_out_impact_rupees=_float(row.leave_one_out_impact_rupees),
        leave_one_out_impact_pct=_float(row.leave_one_out_impact_pct),
        leave_one_out_stock_xirr=_float(row.leave_one_out_stock_xirr),
        leave_one_out_diversified_xirr=_float(row.leave_one_out_diversified_xirr),
        leave_one_out_annualized_advantage_pp=_float(row.leave_one_out_annualized_advantage_pp),
        leave_one_out_mean_portfolio_impact_pp=_float(row.leave_one_out_mean_portfolio_impact_pp),
        leave_one_out_median_portfolio_impact_pp=_float(
            row.leave_one_out_median_portfolio_impact_pp
        ),
        leave_one_out_mean_return_advantage_pp=_float(row.leave_one_out_mean_return_advantage_pp),
        leave_one_out_median_return_advantage_pp=_float(
            row.leave_one_out_median_return_advantage_pp
        ),
        removal_flips_result=row.removal_flips_result,
        note=row.note,
    )


@router.get(
    "/one-year-continuous-loss",
    response_model=ContinuousLossBacktestResponse,
)
def one_year_continuous_loss_backtest(
    session: Session = Depends(get_db),
) -> ContinuousLossBacktestResponse:
    """Run the first-buy-price continuous-loss diversification strategy."""
    result = run_continuous_loss_backtest(session)
    return ContinuousLossBacktestResponse(
        methodology=result.methodology,
        closed_episodes=result.closed_episodes,
        triggered_episodes=result.triggered_episodes,
        no_trigger_episodes=result.no_trigger_episodes,
        excluded_episodes=result.excluded_episodes,
        trigger_rate_pct=float(result.trigger_rate_pct),
        total_trigger_proceeds=float(result.total_trigger_proceeds),
        common_end_date=(result.common_end_date.isoformat() if result.common_end_date else None),
        stock_end_value=float(result.stock_end_value),
        diversified_end_value=float(result.diversified_end_value),
        net_impact_rupees=float(result.net_impact_rupees),
        stock_xirr=_float(result.stock_xirr),
        diversified_xirr=_float(result.diversified_xirr),
        annualized_advantage_pp=_float(result.annualized_advantage_pp),
        terminal_value_uplift_pct=_float(result.terminal_value_uplift_pct),
        mean_portfolio_impact_pp=_float(result.mean_portfolio_impact_pp),
        median_portfolio_impact_pp=_float(result.median_portfolio_impact_pp),
        largest_portfolio_impact_pp=_float(result.largest_portfolio_impact_pp),
        equal_capital_start_value=float(result.equal_capital_start_value),
        hold_equal_capital_end_value=float(result.hold_equal_capital_end_value),
        diversified_equal_capital_end_value=float(result.diversified_equal_capital_end_value),
        equal_capital_net_difference=float(result.equal_capital_net_difference),
        mean_return_advantage_pp=_float(result.mean_return_advantage_pp),
        median_return_advantage_pp=_float(result.median_return_advantage_pp),
        positive_effect_sum_pp=float(result.positive_effect_sum_pp),
        negative_effect_sum_pp=float(result.negative_effect_sum_pp),
        stock_return_pct=_float(result.stock_return_pct),
        diversified_return_pct=_float(result.diversified_return_pct),
        return_uplift_pct=_float(result.return_uplift_pct),
        positive_episodes=result.positive_episodes,
        negative_episodes=result.negative_episodes,
        positive_episode_rate_pct=_float(result.positive_episode_rate_pct),
        top_episode_contribution_pct=_float(result.top_episode_contribution_pct),
        top_three_contribution_pct=_float(result.top_three_contribution_pct),
        contribution_hhi=_float(result.contribution_hhi),
        conclusion=result.conclusion,
        conclusion_text=result.conclusion_text,
        episodes=[_episode_response(row) for row in result.episodes],
    )
