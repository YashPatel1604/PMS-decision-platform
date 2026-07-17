"""Full Milestone 4 analysis orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from pms_platform.analytics.episode_performance import analyze_closed_episodes
from pms_platform.analytics.post_exit import analyze_post_exit_performance


@dataclass(frozen=True)
class FullAnalysisSummary:
    """Combined ownership and post-exit analysis summary."""

    ownership_ok: int
    ownership_insufficient: int
    cash_flow_rows: int
    post_exit_ok: int
    post_exit_insufficient: int


def run_full_episode_analysis(session: Session) -> FullAnalysisSummary:
    """Run ownership-period and post-exit analytics in sequence."""
    ownership = analyze_closed_episodes(session)
    post_exit = analyze_post_exit_performance(session)
    return FullAnalysisSummary(
        ownership_ok=ownership.analyzed,
        ownership_insufficient=ownership.insufficient,
        cash_flow_rows=ownership.cash_flow_rows,
        post_exit_ok=post_exit.analyzed,
        post_exit_insufficient=post_exit.insufficient,
    )
