"""Charts direct DB writes when approval workflow enabled (no Samir gate)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pms_platform.api.main import app
from pms_platform.auth.service import create_user
from pms_platform.config import settings
from pms_platform.db.base import Base
from pms_platform.market_data.nse_bhav_store import sync_bhav_file
from pms_platform.models.charts_range import ChartsRangeRow

FIXTURES = Path(__file__).parent / "fixtures" / "pivot"


def _range_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Range "
    ws.append(["Name", "High", "Low"])
    ws.append([None, None, "Check lows support"])
    ws.append(
        [
            "Reliance",
            1600,
            1000,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            '=VLOOKUP(A3&"EQ",BhavCopy_NSE_CM!A:U,19,0)',
        ]
    )
    wb.save(path)
    wb.close()


@pytest.fixture
def charts_db_api(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "auth_disabled", False)
    monkeypatch.setattr(settings, "auth_secret", "charts-test-auth-secret-key-32b!")
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "feature_approval_workflow", True)

    path = tmp_path / "Charts - Copy.xlsx"
    _range_book(path)
    monkeypatch.setattr(
        "pms_platform.market_data.charts_dashboard.charts_workbook_path",
        lambda folder=None: path,
    )
    monkeypatch.setattr(
        "pms_platform.market_data.nse_bhav_store.settings.upload_dir",
        str(tmp_path),
    )

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
    create_user(session, email="julesh@local", password="1234", display_name="Julesh", role="client")
    sync_bhav_file(session, FIXTURES / "bhav_2026-08-19.csv")
    session.commit()
    session.close()
    return factory


def _login(client: TestClient) -> None:
    assert (
        client.post("/auth/login", json={"email": "julesh@local", "password": "1234"}).status_code
        == 200
    )


def test_charts_levels_write_immediately(charts_db_api) -> None:
    client = TestClient(app)
    _login(client)

    seed = client.get("/strategy/charts/dashboard?as_of=2026-08-19")
    assert seed.status_code == 200

    patch = client.patch(
        "/strategy/charts/levels",
        json={"excel_row": 3, "high": 1700, "low": 1100},
    )
    assert patch.status_code == 200
    assert patch.json()["high"] == 1700.0

    dash = client.get("/strategy/charts/dashboard?as_of=2026-08-19")
    rel = dash.json()["rows"][0]
    assert rel["high"] == 1700.0
    assert rel["low"] == 1100.0

    session = charts_db_api()
    try:
        row = session.scalar(select(ChartsRangeRow).where(ChartsRangeRow.excel_row == 3))
        assert row is not None
        assert float(row.high) == 1700.0
    finally:
        session.close()
