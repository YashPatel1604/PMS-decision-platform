"""Pivot firm selection centralization tests."""

from __future__ import annotations

from pms_platform.approval.service import approve_request, create_draft, submit_request
from pms_platform.auth.passwords import hash_password
from pms_platform.domain.pivot_selection import official_selection, resolve_selection
from pms_platform.models.user import User
from pms_platform.read_context import ReadContext


def _user(session, *, email: str, role: str) -> User:
    u = User(
        email=email,
        password_hash=hash_password("x"),
        display_name=email.split("@")[0],
        role=role,
    )
    session.add(u)
    session.flush()
    return u


def test_selection_overlay_official_vs_mine(session) -> None:
    julesh = _user(session, email="j@t.com", role="client")
    samir = _user(session, email="s@t.com", role="admin")
    req = create_draft(
        session,
        proposer=julesh,
        title="Pivot selection",
        domain="pivot",
        operations=[
            {
                "entity_kind": "pivot_firm_selection",
                "entity_id": "firm_selection",
                "operation_type": "replace",
                "base_row_version": 1,
                "before_state": {"symbols": ["AAA"]},
                "after_state": {"symbols": ["AAA", "BBB"]},
            }
        ],
    )
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    session.flush()

    official = resolve_selection(session, ReadContext.official(), fallback_portfolio_symbols=["AAA"])
    mine = resolve_selection(
        session, ReadContext.mine(julesh.user_id), fallback_portfolio_symbols=["AAA"]
    )
    assert official["symbols"] == ["AAA"]
    assert mine["symbols"] == ["AAA", "BBB"]

    approve_request(session, reviewer=samir, change_request_id=req.change_request_id)
    session.flush()
    assert official_selection(session) == ["AAA", "BBB"]
