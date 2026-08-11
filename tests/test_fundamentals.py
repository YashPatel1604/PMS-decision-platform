"""Tests for quarterly fundamentals ingestion and computed snapshots."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from pms_platform.fundamentals.compute import compute_snapshots_for_identifier, pct_change, pp_change
from pms_platform.fundamentals.import_csv import import_quarterly_fundamentals
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.models import CompanyFundamentalsQuarterly, FundamentalSnapshot, ImportBatch, Security

FIXTURE = Path("tests/fixtures/market_data/fundamentals/quarterly_fundamentals.csv")


@pytest.fixture
def market_security(session, import_batch: ImportBatch) -> Security:
    row = Security(
        security_id="SEC999",
        portfolio_name="TestCo",
        current_nse_symbol="TESTCO",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


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


def test_pct_change_null_safe() -> None:
    assert pct_change(Decimal("110"), Decimal("100")) == Decimal("10")
    assert pct_change(Decimal("110"), None) is None
    assert pct_change(None, Decimal("100")) is None
    assert pct_change(Decimal("110"), Decimal("0")) is None


def test_pp_change_null_safe() -> None:
    assert pp_change(Decimal("14"), Decimal("12")) == Decimal("2")
    assert pp_change(None, Decimal("12")) is None


def test_import_quarterly_fundamentals_idempotent(
    session, heritage_security, mosl_security, market_security
) -> None:
    first = import_quarterly_fundamentals(session, FIXTURE)
    session.commit()
    assert first.inserted == 15
    assert first.invalid == 0

    second = import_quarterly_fundamentals(session, FIXTURE)
    assert second.inserted == 0
    assert second.skipped == 15

    count = session.scalar(select(func.count()).select_from(CompanyFundamentalsQuarterly))
    assert count == 15


def test_recompute_heritage_sales_yoy(
    session, heritage_security, mosl_security, market_security
) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    session.commit()

    snapshot = session.scalar(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier_type == "PORTFOLIO_NAME",
            FundamentalSnapshot.identifier == "Heritage",
            FundamentalSnapshot.fiscal_year == 2025,
            FundamentalSnapshot.fiscal_quarter == "Q1",
        )
    )
    assert snapshot is not None
    assert snapshot.sales_yoy_pct == Decimal("25.0000")
    assert snapshot.sales_qoq_pct == Decimal("8.6957")
    assert snapshot.opm_delta_pp == Decimal("2.00")
    assert snapshot.computation_version == "1.0"

    heritage_rows = session.scalars(
        select(CompanyFundamentalsQuarterly).where(
            CompanyFundamentalsQuarterly.identifier == "Heritage"
        )
    ).all()
    computed = compute_snapshots_for_identifier(list(heritage_rows))
    latest = [row for row in computed if row.fiscal_year == 2025 and row.fiscal_quarter == "Q1"][0]
    assert latest.pat_yoy_pct == Decimal("25")


def test_resolve_security_id_on_import(session, mosl_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    session.commit()
    row = session.scalar(
        select(CompanyFundamentalsQuarterly).where(
            CompanyFundamentalsQuarterly.identifier == "MOTILALOFS"
        )
    )
    assert row is not None
    assert row.security_id == "SEC040"


def test_seed_file_meets_phase3_exit_criteria() -> None:
    seed = Path("docker/market_data_seed/fundamentals/quarterly_fundamentals.csv")
    assert seed.exists()
    lines = seed.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 1
    companies = {line.split(",")[2] for line in lines[1:]}
    quarters = {line.split(",")[5] for line in lines[1:]}
    assert len(companies) >= 50
    assert len(quarters) >= 4
