"""Golden regression tests for Heritage / MOSL fundamentals metrics."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from pms_platform.fundamentals.import_csv import import_quarterly_fundamentals
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.models import FundamentalSnapshot, ImportBatch, Security

FIXTURE = Path("tests/fixtures/market_data/fundamentals/quarterly_fundamentals.csv")

GOLDEN_HERITAGE_Q1FY25 = {
    "sales": Decimal("1000.00"),
    "sales_yoy_pct": Decimal("25.0000"),
    "sales_qoq_pct": Decimal("8.6957"),
    "opm_delta_pp": Decimal("2.00"),
    "pat_yoy_pct": Decimal("25.0000"),
}

GOLDEN_MOSL_Q1FY25 = {
    "sales": Decimal("1500.00"),
    "sales_yoy_pct": Decimal("25.0000"),
    "opm_delta_pp": Decimal("2.00"),
}


@pytest.fixture
def heritage_security(session, import_batch: ImportBatch) -> Security:
    row = Security(
        security_id="SEC014",
        portfolio_name="Heritage",
        current_nse_symbol="HERITGFOOD",
        bse_code="524470",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def mosl_security(session, import_batch: ImportBatch) -> Security:
    row = Security(
        security_id="SEC040",
        portfolio_name="MOSL",
        current_nse_symbol="MOTILALOFS",
        bse_code="532167",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.parametrize(
    ("identifier_type", "identifier", "golden"),
    [
        ("PORTFOLIO_NAME", "Heritage", GOLDEN_HERITAGE_Q1FY25),
        ("NSE_SYMBOL", "MOTILALOFS", GOLDEN_MOSL_Q1FY25),
    ],
)
def test_golden_fundamentals_q1fy25(
    session,
    heritage_security,
    mosl_security,
    identifier_type: str,
    identifier: str,
    golden: dict[str, Decimal],
) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    session.commit()

    snapshot = session.scalar(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier_type == identifier_type,
            FundamentalSnapshot.identifier == identifier,
            FundamentalSnapshot.fiscal_year == 2025,
            FundamentalSnapshot.fiscal_quarter == "Q1",
        )
    )
    assert snapshot is not None
    for field, expected in golden.items():
        assert getattr(snapshot, field) == expected, field
