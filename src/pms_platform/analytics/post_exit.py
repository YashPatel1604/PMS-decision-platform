"""Post-exit performance and sell-quality assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pms_platform.analytics.benchmark import compute_benchmark_period_return, primary_benchmark_code
from pms_platform.analytics.portfolio_value import (
    compute_portfolio_period_return,
    list_security_trading_dates,
)
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.lookup import lookup_daily_price
from pms_platform.models import DailyPrice, InvestmentEpisode, PostExitPerformance, SellAssessment
from pms_platform.models.enums import EpisodeStatus

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_ZERO = Decimal("0")
_PREMATURE_EXCESS_THRESHOLD = Decimal("15")
_LOSS_AVOIDED_THRESHOLD = Decimal("-10")


@dataclass(frozen=True)
class PostExitSummary:
    """Aggregate post-exit analysis outcome."""

    analyzed: int
    insufficient: int


def _latest_price_date(session: Session, security_id: str) -> date | None:
    return session.scalar(
        select(DailyPrice.trade_date)
        .where(DailyPrice.security_id == security_id)
        .order_by(DailyPrice.trade_date.desc())
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
    for trade_date in list_security_trading_dates(session, security_id, start_date, end_date):
        observation = lookup_daily_price(session, security_id, trade_date)
        if observation is None or observation.adjusted_close <= 0:
            continue
        move_pct = ((observation.adjusted_close / exit_price) - _ONE) * _HUNDRED
        max_gain = max(max_gain, move_pct)
        max_loss = min(max_loss, move_pct)
    return max_gain, max_loss


def assess_exit_quality(
    *,
    security_return_after_exit: Decimal | None,
    benchmark_return_after_exit: Decimal | None,
    maximum_gain_after_exit: Decimal | None,
    maximum_loss_after_exit: Decimal | None,
    data_quality_status: str,
) -> tuple[str, str]:
    """Return an explainable exit assessment label and reason."""
    if data_quality_status != "OK" or security_return_after_exit is None:
        return "INSUFFICIENT_DATA", "Missing post-exit price history"

    reasons: list[str] = []

    if (
        maximum_loss_after_exit is not None
        and maximum_loss_after_exit <= _LOSS_AVOIDED_THRESHOLD
        and security_return_after_exit <= _ZERO
    ):
        return (
            "LOSS_AVOIDED",
            f"Security fell up to {maximum_loss_after_exit:.2f}% after exit",
        )

    if (
        benchmark_return_after_exit is not None
        and security_return_after_exit - benchmark_return_after_exit
        > _PREMATURE_EXCESS_THRESHOLD
        and security_return_after_exit > _ZERO
    ):
        return (
            "PREMATURE_EXIT",
            (
                f"Security returned {security_return_after_exit:.2f}% after exit "
                f"versus benchmark {benchmark_return_after_exit:.2f}%"
            ),
        )

    if (
        maximum_gain_after_exit is not None
        and security_return_after_exit < _ZERO
        and maximum_gain_after_exit > _ZERO
    ):
        reasons.append("Exit preceded a later rebound")

    if security_return_after_exit < _ZERO and (
        maximum_loss_after_exit is None or maximum_loss_after_exit < security_return_after_exit
    ):
        return "GOOD_EXIT", f"Security continued lower after exit ({security_return_after_exit:.2f}%)"

    if reasons:
        return "NEUTRAL_EXIT", "; ".join(reasons)
    return "NEUTRAL_EXIT", "No strong evidence of a good or premature exit"


def analyze_post_exit_performance(session: Session) -> PostExitSummary:
    """Compute post-exit metrics and sell assessments for closed episodes."""
    session.execute(delete(SellAssessment))
    session.execute(delete(PostExitPerformance))
    session.flush()

    benchmark_code = primary_benchmark_code()
    episodes = session.scalars(
        select(InvestmentEpisode).where(
            InvestmentEpisode.status == EpisodeStatus.CLOSED.value,
            InvestmentEpisode.exit_date.is_not(None),
        )
    ).all()

    analyzed = 0
    insufficient = 0

    for episode in episodes:
        assert episode.exit_date is not None
        price_security_id = resolve_price_security_id(
            session,
            episode.security_id,
            episode.exit_date,
        )
        comparison_date = _latest_price_date(session, price_security_id)
        if comparison_date is None or comparison_date <= episode.exit_date:
            insufficient += 1
            status = "INSUFFICIENT"
            security_return = None
            portfolio_return = None
            benchmark_return = None
            max_gain = None
            max_loss = None
        else:
            exit_price = lookup_daily_price(session, price_security_id, episode.exit_date)
            end_price = lookup_daily_price(session, price_security_id, comparison_date)
            if (
                exit_price is None
                or end_price is None
                or exit_price.adjusted_close <= 0
            ):
                insufficient += 1
                status = "INSUFFICIENT"
                security_return = None
                portfolio_return = None
                benchmark_return = None
                max_gain = None
                max_loss = None
            else:
                security_return = (
                    (end_price.adjusted_close / exit_price.adjusted_close) - _ONE
                ) * _HUNDRED
                portfolio = compute_portfolio_period_return(
                    session,
                    start_date=episode.exit_date,
                    end_date=comparison_date,
                )
                benchmark = compute_benchmark_period_return(
                    session,
                    benchmark_code=benchmark_code,
                    start_date=episode.exit_date,
                    end_date=comparison_date,
                )
                portfolio_return = portfolio.total_return_pct if portfolio else None
                benchmark_return = benchmark.total_return_pct if benchmark else None
                max_gain, max_loss = _price_path_extremes(
                    session,
                    price_security_id,
                    episode.exit_date,
                    comparison_date,
                )
                status = "OK" if benchmark is not None else "INSUFFICIENT"
                if status == "OK":
                    analyzed += 1
                else:
                    insufficient += 1

        excess_vs_portfolio = (
            security_return - portfolio_return
            if security_return is not None and portfolio_return is not None
            else None
        )
        excess_vs_smallcap = (
            security_return - benchmark_return
            if security_return is not None and benchmark_return is not None
            else None
        )

        session.add(
            PostExitPerformance(
                episode_id=episode.episode_id,
                exit_date=episode.exit_date,
                comparison_date=comparison_date,
                security_return_after_exit=security_return,
                portfolio_return_after_exit=portfolio_return,
                smallcap_return_after_exit=benchmark_return,
                excess_vs_portfolio_after_exit=excess_vs_portfolio,
                excess_vs_smallcap_after_exit=excess_vs_smallcap,
                maximum_gain_after_exit=max_gain,
                maximum_loss_after_exit=max_loss,
                calculation_version="m4-v2",
                data_quality_status=status,
            )
        )

        assessment, reason = assess_exit_quality(
            security_return_after_exit=security_return,
            benchmark_return_after_exit=benchmark_return,
            maximum_gain_after_exit=max_gain,
            maximum_loss_after_exit=max_loss,
            data_quality_status=status,
        )
        session.add(
            SellAssessment(
                episode_id=episode.episode_id,
                exit_assessment=assessment,
                assessment_reason=reason,
                calculation_version="m4-v2",
                data_quality_status=status if status == "OK" else "INSUFFICIENT",
            )
        )

    session.flush()
    return PostExitSummary(analyzed=analyzed, insufficient=insufficient)
