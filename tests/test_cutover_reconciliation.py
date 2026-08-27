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
from pms_platform.models.nse_bhav import PivotPortfolioSymbol
from pms_platform.models.security import Security
from pms_platform.reconciliation.bundle import build_migration_bundle
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
    write_reports(first, out, samir=samir, julesh=julesh)
    payload = json.loads((out / "reconciliation.json").read_text(encoding="utf-8"))
    assert "client_positions" in payload["summary"]
    assert (out / "DATA_RECONCILIATION_REPORT.md").is_file()
    assert (out / "migration_bundle.json").is_file()


def test_bundle_excludes_conflicting_entity(twin_sessions) -> None:
    samir, julesh = twin_sessions
    samir.add(
        ClientPosition(book="client", symbol="RELIANCE", qty=Decimal("100"), row_version=1)
    )
    julesh.add(
        ClientPosition(book="client", symbol="RELIANCE", qty=Decimal("200"), row_version=1)
    )
    samir.add(ClientPosition(book="client", symbol="TCS", qty=Decimal("10"), row_version=1))
    julesh.add(ClientPosition(book="client", symbol="TCS", qty=Decimal("10"), row_version=1))
    samir.commit()
    julesh.commit()

    report = run_cutover_reconciliation(samir, julesh)
    bundle = build_migration_bundle(report, samir, julesh)
    positions = bundle["domains"]["client_positions"]
    assert "client:TCS" in positions
    assert "client:RELIANCE" not in positions
    assert any(ex["key"] == "client:RELIANCE" for ex in bundle["excluded"])


def test_pivot_order_conflict(twin_sessions) -> None:
    samir, julesh = twin_sessions
    samir.add(PivotPortfolioSymbol(symbol="AAA", sort_order=1))
    samir.add(PivotPortfolioSymbol(symbol="BBB", sort_order=2))
    julesh.add(PivotPortfolioSymbol(symbol="BBB", sort_order=1))
    julesh.add(PivotPortfolioSymbol(symbol="AAA", sort_order=2))
    samir.commit()
    julesh.commit()

    report = run_cutover_reconciliation(samir, julesh)
    order_rows = [
        r
        for r in report.rows
        if r.domain == "pivot_portfolio_symbols" and r.key == "__symbol_order__"
    ]
    assert len(order_rows) == 1
    assert order_rows[0].classification == Classification.VALUE_CONFLICT


def test_research_security_only_in_research(twin_sessions, tmp_path: Path) -> None:
    import openpyxl

    samir, julesh = twin_sessions
    samir.add(
        Security(
            security_id="SEC001",
            portfolio_name="Listed Co",
        )
    )
    samir.commit()
    julesh.commit()

    portfolio = tmp_path / "Portfolio"
    portfolio.mkdir()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Security Master"
    ws.append(["security_id", "portfolio_name"])
    ws.append(["SEC001", "Listed Co"])
    ws.append(["SEC002", "Research Only Co"])
    wb.save(portfolio / "SECURITY_MASTER_V1.xlsx")
    wb.close()

    report = run_cutover_reconciliation(samir, julesh, research_dir=tmp_path)
    only = [
        r
        for r in report.rows
        if r.domain == "research_masters"
        and r.classification == Classification.ONLY_IN_RESEARCH
    ]
    assert any("Research Only Co" in str(r.key) for r in only)
