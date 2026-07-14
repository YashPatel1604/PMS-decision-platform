"""Portfolio reconstruction and reconciliation tests."""

from datetime import date
from pathlib import Path

import pytest

from helpers import add_transaction
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.snapshots import parse_snapshot_sheet_date, parse_snapshot_workbook
from pms_platform.ingestion.transactions import import_transaction_master
from pms_platform.models import Security
from pms_platform.models.enums import EventType
from pms_platform.portfolio.cash_engine import liquid_on
from pms_platform.portfolio.name_resolver import resolve_snapshot_name
from pms_platform.portfolio.position_engine import compute_quantities_as_of, portfolio_on
from pms_platform.portfolio.reconciliation import (
    classify_quantity_mismatch_severity,
    reconcile_snapshot_workbook,
)


@pytest.fixture
def loaded_master_data(session) -> None:
    """Load security master and transactions when raw files are available."""
    security_path = Path("data/raw/security_master/SECURITY_MASTER_V1.xlsx")
    transaction_path = Path("data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx")
    if not security_path.exists() or not transaction_path.exists():
        pytest.skip("Raw master files not available")
    import_security_master(session, security_path)
    import_transaction_master(session, transaction_path)
    session.commit()


def test_parse_snapshot_sheet_date() -> None:
    """Sheet names are parsed into ISO dates."""
    assert parse_snapshot_sheet_date("25Jun19", 2019) == date(2019, 6, 25)
    assert parse_snapshot_sheet_date("31stDec24", 2024) == date(2024, 12, 31)
    assert parse_snapshot_sheet_date("11May", 2026) == date(2026, 5, 11)


def test_2012_soft_window_mismatch_is_warning_not_error() -> None:
    """V3 policy: low-confidence mid-2012 snapshot drift does not block the pipeline."""
    assert classify_quantity_mismatch_severity(date(2012, 2, 17), 511, 400) == "WARNING"
    assert classify_quantity_mismatch_severity(date(2012, 8, 7), 511, 443) == "WARNING"
    assert classify_quantity_mismatch_severity(date(2012, 8, 27), 511, 511) is None
    assert classify_quantity_mismatch_severity(date(2012, 8, 27), 511, 400) == "ERROR"
    assert classify_quantity_mismatch_severity(date(2012, 1, 1), 511, 510) is None
    assert classify_quantity_mismatch_severity(date(2015, 1, 1), 317, 1072) == "ERROR"


def test_snapshot_date_prefers_sheet_name_over_stale_a1() -> None:
    """Workbook tabs are authoritative when A1 still carries an older copied date."""
    snapshot_path = Path("data/raw/portfolio_snapshots/Portfolio_2026.xlsx")
    if not snapshot_path.exists():
        pytest.skip("Snapshot workbook not available")

    e2e_rows = [
        row
        for row in parse_snapshot_workbook(snapshot_path)
        if row.source_sheet == "22Jun26" and row.portfolio_name == "E2E"
    ]
    assert e2e_rows
    assert e2e_rows[0].snapshot_date == date(2026, 6, 22)


def test_resolve_snapshot_aliases(session, import_batch) -> None:
    """Known snapshot aliases resolve to Security Master names."""
    security = Security(
        security_id="SEC001", portfolio_name="MOSL", import_batch_id=import_batch.import_batch_id
    )
    session.add(security)
    session.flush()
    assert resolve_snapshot_name("MotilalOFS", [security]) == "MOSL"
    assert resolve_snapshot_name("LiquidBees", [security]) == "LIQUID"


def test_future_transactions_do_not_affect_earlier_date(
    session, import_batch, sample_security
) -> None:
    """Only transactions on or before the as-of date affect reconstruction."""
    add_transaction(
        session, import_batch, sample_security.security_id, date(2020, 1, 1), EventType.BUY, 100, 1
    )
    add_transaction(
        session, import_batch, sample_security.security_id, date(2021, 1, 1), EventType.BUY, 50, 2
    )
    session.commit()

    assert compute_quantities_as_of(session, date(2020, 6, 30))[sample_security.security_id] == 100
    assert compute_quantities_as_of(session, date(2021, 6, 30))[sample_security.security_id] == 150


def test_portfolio_on_matches_2019_snapshot(session, loaded_master_data) -> None:
    """Reconstructed quantities match the 2019-06-25 snapshot workbook."""
    snapshot_path = Path("data/raw/portfolio_snapshots/Portfolio_2019.xlsx")
    if not snapshot_path.exists():
        pytest.skip("Snapshot workbook not available")

    as_of = date(2019, 6, 25)
    positions = portfolio_on(session, as_of)
    reconstructed = {position.portfolio_name: position.quantity for position in positions}

    snapshot_rows = [
        row for row in parse_snapshot_workbook(snapshot_path) if row.snapshot_date == as_of
    ]
    assert snapshot_rows

    securities = session.query(Security).all()
    for row in snapshot_rows:
        resolved = resolve_snapshot_name(row.portfolio_name, securities)
        if resolved in {None, "LIQUID"}:
            continue
        assert reconstructed.get(resolved) == row.quantity


def test_liquid_holding_reconstruction(session, loaded_master_data) -> None:
    """LiquidCase balance is reconstructed separately from equities."""
    liquid = liquid_on(session, date(2026, 7, 1))
    assert liquid is not None
    assert liquid.quantity > 0


def test_reconciliation_report_generated(session, loaded_master_data) -> None:
    """Reconciliation returns structured mismatches instead of failing silently."""
    snapshot_path = Path("data/raw/portfolio_snapshots/Portfolio_2019.xlsx")
    if not snapshot_path.exists():
        pytest.skip("Snapshot workbook not available")

    mismatches = reconcile_snapshot_workbook(session, snapshot_path, as_of_date=date(2019, 6, 25))
    assert mismatches == []
