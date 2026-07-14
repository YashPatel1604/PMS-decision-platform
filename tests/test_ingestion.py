"""Ingestion tests."""

from pathlib import Path

import pytest
from sqlalchemy import select

from pms_platform.ingestion.common import is_liquid_holding
from pms_platform.ingestion.securities import import_security_master
from pms_platform.ingestion.transactions import (
    import_transaction_master,
    parse_transaction_workbook,
)
from pms_platform.models import LiquidTransaction, Security


def test_is_liquid_holding() -> None:
    """LiquidCase and aliases are recognized as liquid holdings."""
    assert is_liquid_holding("LiquidCase") is True
    assert is_liquid_holding("Amara Raja") is False


def test_parse_transaction_workbook_skips_summary_rows() -> None:
    """Per-stock total rows without dates are excluded from parsed transactions."""
    path = Path("data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx")
    if not path.exists():
        pytest.skip("Raw transaction file not available")

    rows, summary_skipped = parse_transaction_workbook(path)
    assert summary_skipped == 76
    assert len(rows) == 420
    assert all(row.event_date for row in rows)
    assert all(row.event_type for row in rows)


def test_import_security_master_real_file(session) -> None:
    """All 75 securities load from the Security Master."""
    path = Path("data/raw/security_master/SECURITY_MASTER_V1.xlsx")
    if not path.exists():
        pytest.skip("Raw security master not available")

    result = import_security_master(session, path)
    session.commit()

    securities = session.scalars(select(Security)).all()
    assert len(securities) == 75
    assert result.inserted == 75

    repeat = import_security_master(session, path)
    session.commit()
    assert repeat.inserted == 0
    assert repeat.skipped == 75


def test_import_transaction_master_idempotent(session) -> None:
    """Re-running transaction import does not create duplicate rows."""
    security_path = Path("data/raw/security_master/SECURITY_MASTER_V1.xlsx")
    transaction_path = Path("data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx")
    if not security_path.exists() or not transaction_path.exists():
        pytest.skip("Raw files not available")

    import_security_master(session, security_path)
    first = import_transaction_master(session, transaction_path)
    session.commit()

    assert first.equity_inserted + first.liquid_inserted > 0
    assert session.scalar(select(LiquidTransaction).limit(1)) is not None

    second = import_transaction_master(session, transaction_path)
    session.commit()
    assert second.equity_inserted == 0
    assert second.liquid_inserted == 0
    assert second.equity_skipped == first.equity_inserted
    assert second.liquid_skipped == first.liquid_inserted


def test_liquid_transactions_not_in_securities(session) -> None:
    """LiquidCase never appears in the Security Master."""
    path = Path("data/raw/security_master/SECURITY_MASTER_V1.xlsx")
    if not path.exists():
        pytest.skip("Raw security master not available")

    import_security_master(session, path)
    session.commit()
    names = {security.portfolio_name for security in session.scalars(select(Security)).all()}
    assert "LiquidCase" not in names
