"""Research goals CRUD helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.research_document import ResearchGoal

_ALLOWED_STATUSES = frozenset({"proposed", "accepted", "done", "dismissed"})


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
    cleaned_status = (status or "accepted").strip().lower()
    if cleaned_status not in _ALLOWED_STATUSES:
        raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUSES)}")
    cleaned_title = title.strip()
    if not cleaned_title:
        raise ValueError("title is required")

    goal = ResearchGoal(
        security_id=security_id,
        title=cleaned_title,
        rationale=(rationale or "").strip() or None,
        priority=int(priority),
        status=cleaned_status,
        source_cache_id=source_cache_id,
        created_by_user=created_by_user,
    )
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal


def accept_agenda_item(
    session: Session,
    *,
    security_id: str,
    title: str,
    rationale: str | None = None,
    priority: int = 0,
    source_cache_id: int | None = None,
    created_by_user: str | None = None,
) -> ResearchGoal:
    """Accept one research-agenda row from a brief into durable goals."""
    return create_goal(
        session,
        security_id=security_id,
        title=title,
        rationale=rationale,
        priority=priority,
        status="accepted",
        source_cache_id=source_cache_id,
        created_by_user=created_by_user,
    )


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
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("title is required")
        goal.title = cleaned
    if rationale is not None:
        goal.rationale = rationale.strip() or None
    if priority is not None:
        goal.priority = int(priority)
    if status is not None:
        cleaned_status = status.strip().lower()
        if cleaned_status not in _ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUSES)}")
        goal.status = cleaned_status
    session.commit()
    session.refresh(goal)
    return goal
