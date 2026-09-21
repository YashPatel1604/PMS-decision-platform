"""SCA holdings qty applies immediately (no Samir approval)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from pms_platform.api.main import app
from pms_platform.models.client_position import ClientPosition
from test_change_requests_api import _login, approval_api  # noqa: F401 — pytest fixtures


def test_sca_qty_applies_immediately(approval_api) -> None:
    client = TestClient(app)
    _login(client, "julesh@local")

    patch = client.patch(
        "/strategy/client-portfolio/positions/ASHAPURMIN/qty?book=sca",
        json={"qty": 500},
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["status"] == "applied"
    assert body["qty"] == 500

    official = client.get("/strategy/client-portfolio/dashboard?book=sca&view=official")
    assert official.status_code == 200
    row = next(
        (r for r in official.json()["holdings"] if r.get("symbol") == "ASHAPURMIN"),
        None,
    )
    if row is not None:
        assert row.get("qty") == 500

    session = approval_api()
    try:
        pos = session.scalar(
            select(ClientPosition).where(
                ClientPosition.book == "sca", ClientPosition.symbol == "ASHAPURMIN"
            )
        )
        assert pos is not None
        assert float(pos.qty) == 500
    finally:
        session.close()
