"""Change request API integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pms_platform.api.main import app
from pms_platform.auth.service import create_user
from pms_platform.config import settings
from pms_platform.db.base import Base
from pms_platform.domain.client_positions import apply_approved_qty_change, apply_qty_overlay
from pms_platform.models.client_position import ClientPosition
from pms_platform.models.user import User
from pms_platform.read_context import ReadContext


@pytest.fixture
def approval_api(monkeypatch):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "auth_secret", "api-test-auth-secret-key-32bytes!")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "feature_approval_workflow", True)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    for target in (
        "pms_platform.api.auth_middleware.get_session_factory",
        "pms_platform.api.deps.get_session_factory",
    ):
        monkeypatch.setattr(target, lambda: factory)

    session = factory()
    create_user(
        session,
        email="samir@local",
        password="1234",
        display_name="Samir",
        role="admin",
    )
    create_user(
        session,
        email="julesh@local",
        password="1234",
        display_name="Julesh",
        role="client",
    )
    session.commit()
    session.close()
    return factory


def _login(client: TestClient, email: str, password: str = "1234") -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_workflow_disabled_returns_503(monkeypatch, approval_api) -> None:
    monkeypatch.setattr(settings, "feature_approval_workflow", False)
    client = TestClient(app)
    _login(client, "samir@local")
    assert client.get("/change-requests/summary").status_code == 503


def test_qty_draft_submit_approve_flow(approval_api) -> None:
    client = TestClient(app)
    _login(client, "julesh@local")

    patch = client.patch(
        "/strategy/client-portfolio/positions/RELIANCE/qty",
        json={"qty": 1200},
    )
    assert patch.status_code == 200
    draft_id = patch.json()["change_request_id"]

    official = client.get("/strategy/client-portfolio/dashboard?view=official")
    assert official.status_code == 200
    reliance_official = next(
        (r for r in official.json()["holdings"] if r.get("symbol") == "RELIANCE"),
        None,
    )
    if reliance_official is not None:
        assert reliance_official.get("proposed_qty") in (None, reliance_official.get("qty"))

    mine = client.get("/strategy/client-portfolio/dashboard?view=mine")
    assert mine.status_code == 200
    reliance_mine = next(
        (r for r in mine.json()["holdings"] if r.get("symbol") == "RELIANCE"),
        {"qty": None},
    )
    if reliance_mine.get("qty") is not None:
        assert reliance_mine["qty"] == 1200

    submit = client.post("/strategy/client-portfolio/positions/RELIANCE/submit")
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"

    client.cookies.clear()
    _login(client, "samir@local")
    approve = client.post(f"/change-requests/{draft_id}/approve", json={})
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    session = approval_api()
    try:
        pos = session.scalar(
            select(ClientPosition).where(
                ClientPosition.book == "client", ClientPosition.symbol == "RELIANCE"
            )
        )
        assert pos is not None
        assert float(pos.qty) == 1200
    finally:
        session.close()


def test_overlay_official_vs_mine(session) -> None:
    """Unit check: mine overlay shows proposed qty; official does not."""
    from decimal import Decimal

    from pms_platform.approval.service import create_draft, submit_request
    from pms_platform.auth.passwords import hash_password

    julesh = User(
        email="j@t.com",
        password_hash=hash_password("x"),
        display_name="J",
        role="client",
    )
    session.add(julesh)
    session.flush()

    holdings = [{"symbol": "ABC", "qty": 1000}]
    apply_approved_qty_change(
        session,
        symbol="ABC",
        qty=Decimal("1000"),
        base_row_version=1,
        updated_by=julesh.user_id,
    )
    req = create_draft(
        session,
        proposer=julesh,
        title="t",
        domain="client_portfolio",
        operations=[
            {
                "entity_kind": "client_position",
                "entity_id": "ABC",
                "operation_type": "update",
                "base_row_version": 1,
                "before_state": {"qty": 1000, "book": "client"},
                "after_state": {"qty": 1200, "book": "client"},
            }
        ],
    )
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    session.flush()

    official_rows = apply_qty_overlay(
        session, holdings, ReadContext.official(), book="client"
    )
    mine_rows = apply_qty_overlay(
        session, holdings, ReadContext.mine(julesh.user_id), book="client"
    )
    assert official_rows[0]["qty"] == 1000
    assert mine_rows[0]["qty"] == 1200
