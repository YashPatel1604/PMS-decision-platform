"""Approval workflow state machine and permissions."""

from __future__ import annotations

import pytest

from pms_platform.approval.service import (
    ApprovalError,
    approve_request,
    create_draft,
    reject_request,
    submit_request,
    user_has_permission,
)
from pms_platform.auth.passwords import hash_password
from pms_platform.auth.permissions import PERMISSION_APPROVE_BUSINESS
from pms_platform.models.user import User


def _user(session, *, email: str, role: str) -> User:
    u = User(
        email=email,
        password_hash=hash_password("test-only-password"),
        display_name=email.split("@")[0],
        role=role,
    )
    session.add(u)
    session.flush()
    return u


def test_julesh_cannot_approve(session) -> None:
    julesh = _user(session, email="julesh@example.com", role="client")
    assert not user_has_permission(session, julesh, PERMISSION_APPROVE_BUSINESS)


def test_samir_role_has_approve_permission(session) -> None:
    samir = _user(session, email="samir@example.com", role="admin")
    assert user_has_permission(session, samir, PERMISSION_APPROVE_BUSINESS)


def test_draft_submit_approve_flow(session) -> None:
    julesh = _user(session, email="j@example.com", role="client")
    samir = _user(session, email="s@example.com", role="admin")
    req = create_draft(
        session,
        proposer=julesh,
        title="Qty change",
        domain="client_portfolio",
        operations=[
            {
                "entity_kind": "client_position",
                "entity_id": "RELIANCE",
                "operation_type": "update",
                "after_state": {"qty": 1200},
            }
        ],
    )
    assert req.status == "draft"
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    assert req.status == "submitted"
    approve_request(session, reviewer=samir, change_request_id=req.change_request_id)
    assert req.status == "approved"


def test_yash_member_cannot_approve(session) -> None:
    yash = _user(session, email="y@example.com", role="member")
    julesh = _user(session, email="j2@example.com", role="client")
    req = create_draft(session, proposer=julesh, title="t", domain="charts")
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    with pytest.raises(ApprovalError):
        approve_request(session, reviewer=yash, change_request_id=req.change_request_id)


def test_reject_requires_reason(session) -> None:
    samir = _user(session, email="s2@example.com", role="admin")
    julesh = _user(session, email="j3@example.com", role="client")
    req = create_draft(session, proposer=julesh, title="t", domain="charts")
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    with pytest.raises(ApprovalError):
        reject_request(session, reviewer=samir, change_request_id=req.change_request_id, reason="  ")
