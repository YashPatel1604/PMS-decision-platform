"""Thesis conflict flags for human review (never auto-break thesis)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.models.investment_thesis import ThesisConflictFlag

_SEVERITY = frozenset({"low", "medium", "high"})
_STATUS = frozenset({"open", "reviewed", "dismissed"})


def create_conflict_flag(
    session: Session,
    *,
    thesis_id: int,
    security_id: str,
    assumption_affected: str,
    what_changed: str,
    severity: str,
    evidence: str,
    event_id: int | None = None,
    management_explanation: str | None = None,
    investigate_next: str | None = None,
) -> ThesisConflictFlag:
    sev = severity.strip().lower()
    if sev not in _SEVERITY:
        raise ValueError(f"severity must be one of {sorted(_SEVERITY)}")
    row = ThesisConflictFlag(
        thesis_id=thesis_id,
        security_id=security_id,
        event_id=event_id,
        assumption_affected=assumption_affected.strip(),
        what_changed=what_changed.strip(),
        severity=sev,
        evidence=evidence.strip(),
        management_explanation=management_explanation,
        investigate_next=investigate_next,
        status="open",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_conflict_flags(
    session: Session,
    *,
    security_id: str | None = None,
    open_only: bool = True,
) -> list[ThesisConflictFlag]:
    stmt = select(ThesisConflictFlag).order_by(ThesisConflictFlag.created_at.desc())
    if security_id:
        stmt = stmt.where(ThesisConflictFlag.security_id == security_id)
    if open_only:
        stmt = stmt.where(ThesisConflictFlag.status == "open")
    return list(session.scalars(stmt).all())


def update_conflict_flag(
    session: Session,
    flag_id: int,
    *,
    status: str | None = None,
) -> ThesisConflictFlag | None:
    row = session.get(ThesisConflictFlag, flag_id)
    if row is None:
        return None
    if status is not None:
        cleaned = status.strip().lower()
        if cleaned not in _STATUS:
            raise ValueError(f"status must be one of {sorted(_STATUS)}")
        row.status = cleaned
    session.commit()
    session.refresh(row)
    return row
