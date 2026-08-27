"""Change request API routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from pms_platform.api.deps import get_db
from pms_platform.approval.service import (
    ApprovalError,
    approve_request,
    create_draft,
    get_user_draft,
    reject_request,
    submit_request,
    user_has_permission,
    withdraw_request,
)
from pms_platform.auth.permissions import (
    PERMISSION_APPROVE_BUSINESS,
    PERMISSION_VIEW_ALL_SUBMITTED,
)
from pms_platform.config import settings
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.models.change_request import ChangeRequest
from pms_platform.models.user import User

router = APIRouter(prefix="/change-requests", tags=["change-requests"])


def _require_workflow() -> None:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=503, detail="Approval workflow is disabled")


def _get_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        if settings.auth_disabled:
            raise HTTPException(status_code=400, detail="Auth required for approval workflow")
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _serialize_request(req: ChangeRequest, session: Session) -> dict[str, Any]:
    from pms_platform.auth.service import get_user_by_id

    proposer_user = get_user_by_id(session, req.proposer_user_id)
    ops = sorted(req.operations, key=lambda o: o.operation_order)
    return {
        "change_request_id": str(req.change_request_id),
        "title": req.title,
        "reason": req.reason,
        "domain": req.domain,
        "status": req.status,
        "proposer": {
            "user_id": proposer_user.user_id if proposer_user else req.proposer_user_id,
            "display_name": proposer_user.display_name if proposer_user else "—",
        },
        "review_note": req.review_note,
        "conflict_explanation": req.conflict_explanation,
        "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "operations": [
            {
                "change_operation_id": str(op.change_operation_id),
                "operation_order": op.operation_order,
                "entity_kind": op.entity_kind,
                "entity_id": op.entity_id,
                "operation_type": op.operation_type,
                "base_row_version": op.base_row_version,
                "before_state": op.before_state,
                "after_state": op.after_state,
            }
            for op in ops
        ],
    }


class CreateDraftBody(BaseModel):
    title: str
    domain: str
    reason: str | None = None
    operations: list[dict[str, Any]] = Field(default_factory=list)


class RejectBody(BaseModel):
    reason: str


class ApproveBody(BaseModel):
    idempotency_key: str | None = None


@router.get("/summary")
def change_requests_summary(
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, int]:
    _require_workflow()
    user = _get_user(request)
    pending = session.scalar(
        select(func.count())
        .select_from(ChangeRequest)
        .where(ChangeRequest.status == "submitted")
    )
    mine_draft = 1 if get_user_draft(session, user_id=user.user_id, domain="client_portfolio") else 0
    return {
        "pending_submitted": int(pending or 0),
        "my_draft": mine_draft,
    }


@router.get("")
def list_change_requests(
    request: Request,
    session: Session = Depends(get_db),
    status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    _require_workflow()
    user = _get_user(request)
    q = select(ChangeRequest).options(selectinload(ChangeRequest.operations))
    if status:
        q = q.where(ChangeRequest.status == status)
    elif user_has_permission(session, user, PERMISSION_VIEW_ALL_SUBMITTED):
        q = q.where(ChangeRequest.status.in_(("submitted", "approved", "rejected", "conflict")))
    else:
        q = q.where(ChangeRequest.proposer_user_id == user.user_id)
    rows = session.scalars(q.order_by(ChangeRequest.updated_at.desc()).limit(100)).all()
    return [_serialize_request(r, session) for r in rows]


@router.get("/{change_request_id}")
def get_change_request(
    change_request_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    req = session.scalar(
        select(ChangeRequest)
        .options(selectinload(ChangeRequest.operations))
        .where(ChangeRequest.change_request_id == change_request_id)
    )
    if req is None:
        raise HTTPException(status_code=404, detail="Not found")
    if req.proposer_user_id != user.user_id and not user_has_permission(
        session, user, PERMISSION_VIEW_ALL_SUBMITTED
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    return _serialize_request(req, session)


@router.post("", status_code=201)
def post_change_request(
    body: CreateDraftBody,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    try:
        req = create_draft(
            session,
            proposer=user,
            title=body.title,
            domain=body.domain,
            reason=body.reason,
            operations=body.operations,
        )
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _serialize_request(req, session)


@router.post("/{change_request_id}/submit")
def post_submit(
    change_request_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    try:
        req = submit_request(session, actor=user, change_request_id=change_request_id)
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_request(req, session)


@router.post("/{change_request_id}/withdraw")
def post_withdraw(
    change_request_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    try:
        req = withdraw_request(session, actor=user, change_request_id=change_request_id)
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_request(req, session)


@router.post("/{change_request_id}/approve")
def post_approve(
    change_request_id: uuid.UUID,
    body: ApproveBody,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    if not user_has_permission(session, user, PERMISSION_APPROVE_BUSINESS):
        raise HTTPException(status_code=403, detail="Not permitted to approve")
    try:
        req = approve_request(
            session,
            reviewer=user,
            change_request_id=change_request_id,
            idempotency_key=body.idempotency_key,
        )
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_request(req, session)


@router.post("/{change_request_id}/reject")
def post_reject(
    change_request_id: uuid.UUID,
    body: RejectBody,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_workflow()
    user = _get_user(request)
    try:
        req = reject_request(
            session, reviewer=user, change_request_id=change_request_id, reason=body.reason
        )
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_request(req, session)
