"""Client canonical fields (index, mcap_factor) and SCA bank balance in Postgres."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pms_platform.api.main import app
from pms_platform.domain.client_positions import (
    bank_balance_for_book,
    update_position_fields,
)
from pms_platform.models.client_book_settings import ClientBookSettings
from pms_platform.models.client_position import ClientPosition
from test_change_requests_api import _login, approval_api  # noqa: F401 — pytest fixtures


def test_bank_balance_stored_when_workflow_on(approval_api, monkeypatch) -> None:
    from pms_platform.config import settings

    monkeypatch.setattr(settings, "feature_approval_workflow", True)
    session = approval_api()
    try:
        written = bank_balance_for_book(
            session, "sca", excel_bank=Decimal("1000000")
        )
        assert written == Decimal("1000000")
        session.commit()

        row = session.get(ClientBookSettings, "sca")
        assert row is not None
        assert row.bank_balance == Decimal("1000000")
    finally:
        session.close()

    client = TestClient(app)
    _login(client, "julesh@local")
    patch = client.patch(
        "/strategy/client-portfolio/bank-balance?book=sca",
        json={"amount": 2500000},
    )
    assert patch.status_code == 200
    assert patch.json()["bank_balance"] == 2500000


def test_position_fields_patch(approval_api, monkeypatch) -> None:
    from pms_platform.config import settings

    monkeypatch.setattr(settings, "feature_approval_workflow", True)
    session = approval_api()
    try:
        user_id = 1
        pos = update_position_fields(
            session,
            symbol="RELIANCE",
            book="client",
            updated_by=user_id,
            index_label="Nifty 50",
            mcap_factor=Decimal("9.5"),
            touch_index=True,
            touch_mcap_factor=True,
        )
        session.commit()
        assert pos.index_label == "Nifty 50"
        assert pos.mcap_factor == Decimal("9.5")
    finally:
        session.close()

    client = TestClient(app)
    _login(client, "julesh@local")
    patch = client.patch(
        "/strategy/client-portfolio/positions/RELIANCE/fields",
        json={"index_label": "Sensex", "mcap_factor": 10.25},
    )
    assert patch.status_code == 200
    payload = patch.json()
    assert payload["index_label"] == "Sensex"
    assert payload["mcap_factor"] == 10.25

    session = approval_api()
    try:
        pos = session.scalar(
            select(ClientPosition).where(
                ClientPosition.book == "client", ClientPosition.symbol == "RELIANCE"
            )
        )
        assert pos is not None
        assert pos.index_label == "Sensex"
        assert float(pos.mcap_factor) == 10.25
    finally:
        session.close()
