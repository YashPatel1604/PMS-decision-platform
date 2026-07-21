"""Fixed-horizon post-exit performance and dimensional sell assessments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.analytics.benchmark import (
    compute_benchmark_period_return,
    primary_benchmark_code,
)
from pms_platform.analytics.exit_assessment import (
    ExitAssessmentInput,
    assess_exit_quality,
)
from pms_platform.analytics.portfolio_value import (
    compute_portfolio_period_return,
    list_security_trading_dates,
)
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import (
    DailyPrice,
    EpisodePerformance,
    InvestmentEpisode,
    PostExitHorizonPerformance,
    PostExitPerformance,
    SellAssessment,
)
from pms_platform.models.enums import EpisodeStatus

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")
CALCULATION_VERSION = "m5-v2"
FIXED_HORIZONS = (("1Y", 1), ("3Y", 3), ("5Y", 5))


@dataclass(frozen=True)
class PostExitSummary:
    """Aggregate post-exit analysis outcome."""

    analyzed: int
    insufficient: int


def _add_years(value: date, years: int) -> date:
    """Add calendar years while handling a February 29 exit."""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _latest_price_date(session: Session, security_id: str) -> date | None:
    return session.scalar(
        select(DailyPrice.trade_date)
        .where(DailyPrice.security_id == security_id)
        .order_by(DailyPrice.trade_date.desc())
        .limit(1)
    )


def _first_price_date_on_or_after(
    session: Session,
    security_id: str,
    target_date: date,
    latest_date: date,
) -> date | None:
    return session.scalar(
        select(DailyPrice.trade_date)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date >= target_date,
            DailyPrice.trade_date <= latest_date,
        )
        .order_by(DailyPrice.trade_date)
        .limit(1)
    )


def _price_path_extremes(
    session: Session,
    security_id: str,
    start_date: date,
    end_date: date,
) -> tuple[Decimal | None, Decimal | None]:
    start_obs = lookup_daily_price(session, security_id, start_date)
    if start_obs is None or start_obs.adjusted_close <= 0:
        return None, None

    exit_price = start_obs.adjusted_close
    max_gain = _ZERO
    max_loss = _ZERO
    for trade_date in list_security_trading_dates(
        session,
        security_id,
        start_date,
        end_date,
    ):
        observation = lookup_daily_price(session, security_id, trade_date)
        if observation is None or observation.adjusted_close <= 0:
            continue
        move_pct = ((observation.adjusted_close / exit_price) - _ONE) * _HUNDRED
        max_gain = max(max_gain, move_pct)
        max_loss = min(max_loss, move_pct)
    return max_gain, max_loss


def _empty_horizon(
    episode: InvestmentEpisode,
    horizon: str,
    target_date: date | None,
    status: str,
) -> PostExitHorizonPerformance:
    assert episode.exit_date is not None
    return PostExitHorizonPerformance(
        episode_id=episode.episode_id,
        horizon=horizon,
        exit_date=episode.exit_date,
        target_date=target_date,
        comparison_date=None,
        days_after_exit=None,
        security_return_after_exit=None,
        smallcap_return_after_exit=None,
        excess_vs_smallcap_after_exit=None,
        provisional_portfolio_return_after_exit=None,
        provisional_excess_vs_portfolio_after_exit=None,
        calculation_version=CALCULATION_VERSION,
        data_quality_status=status,
    )


def _compute_horizon(
    session: Session,
    episode: InvestmentEpisode,
    horizon: str,
    target_date: date | None,
    latest_date: date | None,
    benchmark_code: str,
) -> PostExitHorizonPerformance:
    assert episode.exit_date is not None
    if latest_date is None or latest_date <= episode.exit_date:
        return _empty_horizon(episode, horizon, target_date, "INSUFFICIENT")
    if target_date is not None and latest_date < target_date:
        return _empty_horizon(episode, horizon, target_date, "NOT_YET_AVAILABLE")

    end_security_id = resolve_price_security_id(
        session,
        episode.security_id,
        target_date or latest_date,
    )
    comparison_date = (
        latest_date
        if target_date is None
        else _first_price_date_on_or_after(
            session,
            end_security_id,
            target_date,
            latest_date,
        )
    )
    if comparison_date is None:
        return _empty_horizon(episode, horizon, target_date, "INSUFFICIENT")

    start_security_id = resolve_price_security_id(
        session,
        episode.security_id,
        episode.exit_date,
    )
    start_price = lookup_daily_price(
        session,
        start_security_id,
        episode.exit_date,
    )
    end_price = lookup_daily_price(
        session,
        end_security_id,
        comparison_date,
    )
    if (
        start_price is None
        or end_price is None
        or start_price.adjusted_close <= 0
        or end_price.adjusted_close <= 0
    ):
        return _empty_horizon(episode, horizon, target_date, "INSUFFICIENT")

    security_return = (
        (end_price.adjusted_close / start_price.adjusted_close) - _ONE
    ) * _HUNDRED
    benchmark = compute_benchmark_period_return(
        session,
        benchmark_code=benchmark_code,
        start_date=episode.exit_date,
        end_date=comparison_date,
    )
    if benchmark is None:
        return _empty_horizon(episode, horizon, target_date, "INSUFFICIENT")

    portfolio = compute_portfolio_period_return(
        session,
        start_date=episode.exit_date,
        end_date=comparison_date,
    )
    portfolio_return = portfolio.total_return_pct if portfolio else None
    return PostExitHorizonPerformance(
        episode_id=episode.episode_id,
        horizon=horizon,
        exit_date=episode.exit_date,
        target_date=target_date,
        comparison_date=comparison_date,
        days_after_exit=(comparison_date - episode.exit_date).days,
        security_return_after_exit=security_return,
        smallcap_return_after_exit=benchmark.total_return_pct,
        excess_vs_smallcap_after_exit=(
            security_return - benchmark.total_return_pct
        ),
        provisional_portfolio_return_after_exit=portfolio_return,
        provisional_excess_vs_portfolio_after_exit=(
            security_return - portfolio_return
            if portfolio_return is not None
            else None
        ),
        calculation_version=CALCULATION_VERSION,
        data_quality_status="OK",
    )


def _assessment_input(
    ownership: EpisodePerformance | None,
    one_year: PostExitHorizonPerformance,
) -> ExitAssessmentInput:
    peak_to_exit_days = None
    if ownership and ownership.peak_price_date:
        peak_to_exit_days = (ownership.exit_date - ownership.peak_price_date).days

    one_year_status = (
        "TOO_RECENT"
        if one_year.data_quality_status == "NOT_YET_AVAILABLE"
        else one_year.data_quality_status
    )
    return ExitAssessmentInput(
        ownership_data_status=(
            ownership.data_quality_status if ownership else "INSUFFICIENT"
        ),
        one_year_data_status=one_year_status,
        holding_days=ownership.holding_days if ownership else 0,
        stock_annualized_return_pct=(
            ownership.stock_annualized_return_pct if ownership else None
        ),
        smallcap_annualized_return_pct=(
            ownership.smallcap_annualized_return if ownership else None
        ),
        days_underperforming_benchmark=(
            ownership.days_underperforming_benchmark if ownership else None
        ),
        ownership_trading_days=(
            ownership.ownership_trading_days if ownership else None
        ),
        max_unrealized_gain_pct=(
            ownership.max_unrealized_gain if ownership else None
        ),
        missed_upside_vs_peak_pct=(
            ownership.missed_upside_vs_peak_pct if ownership else None
        ),
        peak_to_exit_days=peak_to_exit_days,
        continuous_underwater_days=(
            ownership.calendar_days_held_after_first_loss if ownership else None
        ),
        one_year_stock_return_pct=one_year.security_return_after_exit,
        one_year_smallcap_return_pct=one_year.smallcap_return_after_exit,
    )


def analyze_post_exit_performance(session: Session) -> PostExitSummary:
    """Compute latest/fixed horizons and assign every final verdict."""
    session.execute(delete(SellAssessment))
    session.execute(delete(PostExitHorizonPerformance))
    session.execute(delete(PostExitPerformance))
    session.flush()

    benchmark_code = primary_benchmark_code()
    episodes = session.scalars(
        select(InvestmentEpisode).where(
            InvestmentEpisode.status == EpisodeStatus.CLOSED.value,
            InvestmentEpisode.exit_date.is_not(None),
        )
    ).all()
    performance_by_episode = {
        row.episode_id: row
        for row in session.scalars(select(EpisodePerformance)).all()
    }
    analyzed = 0
    insufficient = 0

    for episode in episodes:
        assert episode.exit_date is not None
        latest_security_id = resolve_price_security_id(
            session,
            episode.security_id,
            date.today(),
        )
        latest_date = _latest_price_date(session, latest_security_id)
        horizon_rows: dict[str, PostExitHorizonPerformance] = {}
        for horizon, years in FIXED_HORIZONS:
            row = _compute_horizon(
                session,
                episode,
                horizon,
                _add_years(episode.exit_date, years),
                latest_date,
                benchmark_code,
            )
            session.add(row)
            horizon_rows[horizon] = row

        latest = _compute_horizon(
            session,
            episode,
            "LATEST",
            None,
            latest_date,
            benchmark_code,
        )
        session.add(latest)
        horizon_rows["LATEST"] = latest

        if latest.data_quality_status == "OK":
            analyzed += 1
        else:
            insufficient += 1

        start_security_id = resolve_price_security_id(
            session,
            episode.security_id,
            episode.exit_date,
        )
        max_gain, max_loss = (
            _price_path_extremes(
                session,
                start_security_id,
                episode.exit_date,
                latest.comparison_date,
            )
            if latest.comparison_date is not None
            else (None, None)
        )
        session.add(
            PostExitPerformance(
                episode_id=episode.episode_id,
                exit_date=episode.exit_date,
                comparison_date=latest.comparison_date,
                security_return_after_exit=latest.security_return_after_exit,
                portfolio_return_after_exit=(
                    latest.provisional_portfolio_return_after_exit
                ),
                smallcap_return_after_exit=latest.smallcap_return_after_exit,
                excess_vs_portfolio_after_exit=(
                    latest.provisional_excess_vs_portfolio_after_exit
                ),
                excess_vs_smallcap_after_exit=(
                    latest.excess_vs_smallcap_after_exit
                ),
                maximum_gain_after_exit=max_gain,
                maximum_loss_after_exit=max_loss,
                calculation_version=CALCULATION_VERSION,
                data_quality_status=latest.data_quality_status,
            )
        )

        assessment_input = _assessment_input(
            performance_by_episode.get(episode.episode_id),
            horizon_rows["1Y"],
        )
        result = assess_exit_quality(assessment_input)
        session.add(
            SellAssessment(
                episode_id=episode.episode_id,
                exit_assessment=result.primary,
                assessment_flags=",".join(result.flags),
                ownership_flags=",".join(result.ownership_flags),
                post_exit_flags=",".join(result.post_exit_flags),
                assessment_confidence=result.confidence,
                assessment_evidence=json.dumps(result.evidence, sort_keys=True),
                assessment_reason=result.reason,
                calculation_version=CALCULATION_VERSION,
                data_quality_status=(
                    "OK"
                    if result.primary
                    not in {"INSUFFICIENT_DATA", "TOO_RECENT_TO_JUDGE"}
                    else assessment_input.one_year_data_status
                ),
            )
        )

    session.flush()
    return PostExitSummary(analyzed=analyzed, insufficient=insufficient)
