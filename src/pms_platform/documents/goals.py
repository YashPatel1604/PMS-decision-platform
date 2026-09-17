"""Research goals CRUD helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.research_document import ResearchGoal


def list_goals(
    session: Session,
    *,
    security_id: str | None = None,
    include_dismissed: bool = False,
) -> list[ResearchGoal]:
    stmt = select(ResearchGoal).order_by(ResearchGoal.priority.asc(), ResearchGoal.goal_id.asc())
    if security_id:
        stmt = stmt.where(ResearchGoal.security_id == security_id)
    if not include_dismissed:
        stmt = stmt.where(ResearchGoal.status != "dismissed")
    return list(session.scalars(stmt).all())


def create_goal(
    session: Session,
    *,
    security_id: str,
    title: str,
    rationale: str | None = None,
    priority: int = 0,
    status: str = "accepted",
    source_cache_id: int | None = None,
    created_by_user: str | None = None,
) -> ResearchGoal:
    goal = ResearchGoal(
        security_id=security_id,
        title=title.strip(),
        rationale=(rationale or "").strip() or None,
        priority=priority,
        status=status,
        source_cache_id=source_cache_id,
        created_by_user=created_by_user,
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


def update_goal(
    session: Session,
    goal_id: int,
    *,
    title: str | None = None,
    rationale: str | None = None,
    priority: int | None = None,
    status: str | None = None,
) -> ResearchGoal | None:
    goal = session.get(ResearchGoal, goal_id)
    if goal is None:
        return None
    if title is not None:
        goal.title = title.strip()
    if rationale is not None:
        goal.rationale = rationale.strip() or None
    if priority is not None:
        goal.priority = priority
    if status is not None:
        goal.status = status
    session.commit()
    session.refresh(goal)
    return goal
