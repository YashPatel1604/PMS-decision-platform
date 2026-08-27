"""Change-request state machine and authorization helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.auth.permissions import (
    PERMISSION_APPROVE_BUSINESS,
    PERMISSION_REJECT_BUSINESS,
    ROLE_DEFAULT_PERMISSIONS,
)
from pms_platform.models.change_request import (
    CHANGE_REQUEST_STATUSES,
    AuditEvent,
    ChangeOperation,
    ChangeRequest,
    UserPermission,
)
from pms_platform.models.user import User

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"submitted", "withdrawn"}),
    "submitted": frozenset({"approved", "rejected", "withdrawn", "conflict"}),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
    "approved": frozenset(),
    "conflict": frozenset(),
    "superseded": frozenset(),
}


class ApprovalError(Exception):
    """Business rule violation in approval workflow."""


def user_has_permission(session: Session, user: User, code: str) -> bool:
    explicit = session.scalars(
        select(UserPermission.permission_code).where(UserPermission.user_id == user.user_id)
    ).all()
    if explicit:
        return code in explicit
    return code in ROLE_DEFAULT_PERMISSIONS.get(user.role, frozenset())


def create_draft(
    session: Session,
    *,
    proposer: User,
    title: str,
    domain: str,
    reason: str | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> ChangeRequest:
    if not user_has_permission(session, proposer, "create_draft_changes"):
        raise ApprovalError("not permitted to create drafts")
    req = ChangeRequest(
        title=title,
        domain=domain,
        reason=reason,
        proposer_user_id=proposer.user_id,
        status="draft",
    )
    session.add(req)
    session.flush()
    for idx, op in enumerate(operations or []):
        session.add(
            ChangeOperation(
                change_request_id=req.change_request_id,
                operation_order=idx,
                entity_kind=op["entity_kind"],
                entity_id=op.get("entity_id"),
                operation_type=op["operation_type"],
                base_row_version=op.get("base_row_version"),
                before_state=op.get("before_state"),
                after_state=op.get("after_state"),
                validation_result=op.get("validation_result"),
            )
        )
    _audit(session, actor=proposer, action="change_request.created", change_request=req)
    return req


def submit_request(session: Session, *, actor: User, change_request_id: uuid.UUID) -> ChangeRequest:
    req = session.get(ChangeRequest, change_request_id)
    if req is None:
        raise ApprovalError("change request not found")
    if req.proposer_user_id != actor.user_id:
        raise ApprovalError("only proposer may submit")
    _transition(req, "submitted")
    req.submitted_at = datetime.now(UTC)
    _audit(session, actor=actor, action="change_request.submitted", change_request=req)
    return req


def approve_request(
    session: Session,
    *,
    reviewer: User,
    change_request_id: uuid.UUID,
    idempotency_key: str | None = None,
) -> ChangeRequest:
    if not user_has_permission(session, reviewer, PERMISSION_APPROVE_BUSINESS):
        raise ApprovalError("not permitted to approve business changes")
    req = session.get(ChangeRequest, change_request_id)
    if req is None:
        raise ApprovalError("change request not found")
    if req.status == "approved" and idempotency_key and req.idempotency_key == idempotency_key:
        return req
    if req.status != "submitted":
        raise ApprovalError(f"cannot approve from status {req.status}")
    # ponytail: handler registry applies ops in Phase 5; conflict check hooks here later.
    _transition(req, "approved")
    req.reviewer_user_id = reviewer.user_id
    req.reviewed_at = datetime.now(UTC)
    if idempotency_key:
        req.idempotency_key = idempotency_key
    _audit(session, actor=reviewer, action="change_request.approved", change_request=req)
    return req


def reject_request(
    session: Session,
    *,
    reviewer: User,
    change_request_id: uuid.UUID,
    reason: str,
) -> ChangeRequest:
    if not user_has_permission(session, reviewer, PERMISSION_REJECT_BUSINESS):
        raise ApprovalError("not permitted to reject business changes")
    if not reason.strip():
        raise ApprovalError("rejection reason required")
    req = session.get(ChangeRequest, change_request_id)
    if req is None:
        raise ApprovalError("change request not found")
    _transition(req, "rejected")
    req.reviewer_user_id = reviewer.user_id
    req.review_note = reason.strip()
    req.reviewed_at = datetime.now(UTC)
    _audit(session, actor=reviewer, action="change_request.rejected", change_request=req)
    return req


def _transition(req: ChangeRequest, new_status: str) -> None:
    if new_status not in CHANGE_REQUEST_STATUSES:
        raise ApprovalError(f"invalid status {new_status}")
    allowed = _VALID_TRANSITIONS.get(req.status, frozenset())
    if new_status not in allowed:
        raise ApprovalError(f"cannot transition {req.status} -> {new_status}")
    req.status = new_status


def _audit(
    session: Session,
    *,
    actor: User,
    action: str,
    change_request: ChangeRequest,
) -> None:
    session.add(
        AuditEvent(
            actor_user_id=actor.user_id,
            action=action,
            entity_kind="change_request",
            entity_id=str(change_request.change_request_id),
            change_request_id=change_request.change_request_id,
        )
    )
