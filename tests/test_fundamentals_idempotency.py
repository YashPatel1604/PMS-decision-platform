"""Tests for idempotent fundamental snapshot upserts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from pms_platform.fundamentals.compute import compute_snapshots_for_identifier, dedupe_quarterly_rows
from pms_platform.fundamentals.service import recompute_snapshots_for_identifiers
from pms_platform.models import CompanyFundamentalsQuarterly, FundamentalSnapshot, ImportBatch, Security


def _quarterly_row(
    session,
    batch: ImportBatch,
    *,
    bse: str = "500008",
    period_end: date = date(2026, 3, 31),
    source: str = "NSE:AAA:1",
    provider: str = "nse_xbrl",
    sales: Decimal = Decimal("100"),
) -> CompanyFundamentalsQuarterly:
    row = CompanyFundamentalsQuarterly(
        identifier_type="BSE_CODE",
        identifier=bse,
        fiscal_year=2026,
        fiscal_quarter="Q4",
        period_end_date=period_end,
        sales=sales,
        pat=Decimal("10"),
        opm=Decimal("12"),
        npm=Decimal("10"),
        source=source,
        provider=provider,
        contract_version="1.0",
        retrieved_at=datetime.now(timezone.utc),
        source_file="test",
        source_row=1,
        source_key=f"test:{source}:{period_end.isoformat()}",
        import_batch_id=batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


def test_dedupe_quarterly_rows_prefers_nse_xbrl(session, import_batch: ImportBatch) -> None:
    bse_row = _quarterly_row(
        session,
        import_batch,
        source="bse:1",
        provider="xbrl",
        sales=Decimal("90"),
    )
    nse_row = _quarterly_row(
        session,
        import_batch,
        source="NSE:AAA:1",
        provider="nse_xbrl",
        sales=Decimal("100"),
    )
    deduped = dedupe_quarterly_rows([bse_row, nse_row])
    assert len(deduped) == 1
    assert deduped[0].provider == "nse_xbrl"
    assert deduped[0].sales == Decimal("100")


def test_recompute_snapshots_idempotent_with_multi_source_periods(
    session, import_batch: ImportBatch
) -> None:
    sec = Security(
        security_id="SEC500008",
        portfolio_name="Test",
        bse_code="500008",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(sec)
    session.flush()

    _quarterly_row(session, import_batch, source="bse:1", provider="xbrl")
    _quarterly_row(session, import_batch, source="NSE:AAA:1", provider="nse_xbrl")
    _quarterly_row(
        session,
        import_batch,
        period_end=date(2026, 6, 30),
        source="bse:2",
        provider="xbrl",
    )
    _quarterly_row(
        session,
        import_batch,
        period_end=date(2026, 6, 30),
        source="NSE:AAA:2",
        provider="nse_xbrl",
    )

    rows = session.scalars(
        select(CompanyFundamentalsQuarterly).where(
            CompanyFundamentalsQuarterly.identifier == "500008"
        )
    ).all()
    computed = compute_snapshots_for_identifier(list(rows))
    assert len(computed) == 2

    recompute_snapshots_for_identifiers(session, [("BSE_CODE", "500008")])
    session.flush()
    count1 = session.scalar(
        select(func.count()).select_from(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier == "500008"
        )
    )

    recompute_snapshots_for_identifiers(session, [("BSE_CODE", "500008")])
    session.flush()
    count2 = session.scalar(
        select(func.count()).select_from(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier == "500008"
        )
    )
    assert count1 == 2
    assert count2 == count1
