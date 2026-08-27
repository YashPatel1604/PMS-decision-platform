"""Phase 6 cutover reconciliation tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pms_platform.db.base import Base
from pms_platform.models.client_position import ClientPosition
from pms_platform.reconciliation.cutover import run_cutover_reconciliation
from pms_platform.reconciliation.report import write_reports
from pms_platform.reconciliation.types import Classification


@pytest.fixture
def twin_sessions():
    engines = [create_engine("sqlite+pysqlite:///:memory:") for _ in range(2)]
    factories = []
    for engine in engines:
        Base.metadata.create_all(engine)
        factories.append(sessionmaker(bind=engine, autoflush=False, autocommit=False))
    samir = factories[0]()
    julesh = factories[1]()
    try:
        yield samir, julesh
    finally:
        samir.close()
        julesh.close()
        for engine in engines:
            engine.dispose()


def test_detects_qty_conflict(twin_sessions) -> None:
    samir, julesh = twin_sessions
    samir.add(
        ClientPosition(book="client", symbol="RELIANCE", qty=Decimal("100"), row_version=1)
    )
    julesh.add(
        ClientPosition(book="client", symbol="RELIANCE", qty=Decimal("200"), row_version=1)
    )
    samir.commit()
    julesh.commit()

    report = run_cutover_reconciliation(samir, julesh)
    conflicts = [
        r
        for r in report.rows
        if r.domain == "client_positions"
        and r.classification == Classification.VALUE_CONFLICT
        and r.field == "qty"
    ]
    assert len(conflicts) == 1
    assert conflicts[0].samir_value == "100"
    assert conflicts[0].julesh_value == "200"


def test_identical_positions(twin_sessions) -> None:
    samir, julesh = twin_sessions
    for session in (samir, julesh):
        session.add(
            ClientPosition(
                book="client",
                symbol="TCS",
                qty=Decimal("50"),
                mcap_factor=Decimal("1.5"),
                index_label="Nifty",
                row_version=1,
            )
        )
        session.commit()

    report = run_cutover_reconciliation(samir, julesh)
    qty_rows = [r for r in report.rows if r.domain == "client_positions" and r.field == "qty"]
    assert all(r.classification == Classification.IDENTICAL for r in qty_rows)


def test_report_is_deterministic_except_timestamp(twin_sessions, tmp_path: Path) -> None:
    samir, julesh = twin_sessions
    samir.add(ClientPosition(book="sca", symbol="X", qty=Decimal("1"), row_version=1))
    julesh.add(ClientPosition(book="sca", symbol="X", qty=Decimal("1"), row_version=1))
    samir.commit()
    julesh.commit()

    first = run_cutover_reconciliation(samir, julesh)
    second = run_cutover_reconciliation(samir, julesh)
    assert first.summary == second.summary
    assert [r.as_dict() for r in first.rows] == [r.as_dict() for r in second.rows]

    out = tmp_path / "recon"
    write_reports(first, out)
    payload = json.loads((out / "reconciliation.json").read_text(encoding="utf-8"))
    assert "client_positions" in payload["summary"]
    assert (out / "DATA_RECONCILIATION_REPORT.md").is_file()
