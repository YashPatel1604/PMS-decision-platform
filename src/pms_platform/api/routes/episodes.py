"""Episode analytics API routes."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.analytics.service import run_full_episode_analysis
from pms_platform.db.base import get_session_factory
from pms_platform.models import (
    EpisodePerformance,
    PostExitPerformance,
    Security,
    SellAssessment,
)

router = APIRouter()


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for API handlers."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


class EpisodePerformanceResponse(BaseModel):
    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: str
    exit_date: str
    holding_days: int
    total_invested: float
    total_profit_loss: float
    total_return_pct: float | None
    stock_xirr: float | None
    portfolio_return_pct: float | None
    smallcap_return_pct: float | None
    excess_vs_smallcap: float | None
    excess_vs_portfolio: float | None
    max_drawdown: float | None
    days_below_cost: int | None
    days_underperforming_benchmark: int | None
    exit_assessment: str | None
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
) -> EpisodePerformanceResponse:
    return EpisodePerformanceResponse(
        episode_id=row.episode_id,
        security_id=row.security_id,
        portfolio_name=portfolio_name,
        entry_date=row.entry_date.isoformat(),
        exit_date=row.exit_date.isoformat(),
        holding_days=row.holding_days,
        total_invested=float(row.total_invested),
        total_profit_loss=float(row.total_profit_loss),
        total_return_pct=float(row.total_return_pct) if row.total_return_pct else None,
        stock_xirr=float(row.stock_xirr) if row.stock_xirr else None,
        portfolio_return_pct=float(row.portfolio_return_pct) if row.portfolio_return_pct else None,
        smallcap_return_pct=float(row.smallcap_return_pct) if row.smallcap_return_pct else None,
        excess_vs_smallcap=float(row.excess_vs_smallcap) if row.excess_vs_smallcap else None,
        excess_vs_portfolio=float(row.excess_vs_portfolio) if row.excess_vs_portfolio else None,
        max_drawdown=float(row.max_drawdown) if row.max_drawdown else None,
        days_below_cost=row.days_below_cost,
        days_underperforming_benchmark=row.days_underperforming_benchmark,
        exit_assessment=assessment.exit_assessment if assessment else None,
        assessment_reason=assessment.assessment_reason if assessment else None,
        data_quality_status=row.data_quality_status,
    )


@router.post("/analyze", response_model=AnalysisRunResponse)
def analyze_episodes(session: Session = Depends(get_db)) -> AnalysisRunResponse:
    """Recompute episode analytics and persist results."""
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
    return _performance_response(
        row,
        security.portfolio_name if security else row.security_id,
        assessment,
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
