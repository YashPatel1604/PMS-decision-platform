"""Dashboard summary API routes."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.models import EpisodePerformance, PostExitPerformance, SellAssessment

router = APIRouter()


class DashboardSummaryResponse(BaseModel):
    """High-level counts for the UI home screen."""

    total_episodes: int
    ownership_ok: int
    ownership_insufficient: int
    post_exit_ok: int
    post_exit_insufficient: int
    assessment_counts: dict[str, int]


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

    return DashboardSummaryResponse(
        total_episodes=total,
        ownership_ok=ownership_ok,
        ownership_insufficient=ownership_insufficient,
        post_exit_ok=post_exit_ok,
        post_exit_insufficient=post_exit_insufficient,
        assessment_counts=assessment_counts,
    )
