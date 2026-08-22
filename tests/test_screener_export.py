"""Screener.in export import → snapshot tables."""

from __future__ import annotations

from pathlib import Path

from pms_platform.fundamentals.providers.screener_export import (
    find_latest_screener_export,
    import_screener_export,
)
from pms_platform.models.annual_fundamentals_snapshot import AnnualFundamentalsSnapshot
from pms_platform.models.fundamental_snapshot import FundamentalSnapshot
from pms_platform.models.valuation_snapshot import ValuationSnapshot
from sqlalchemy import select

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "market_data"
    / "fundamentals"
    / "screener"
    / "sample_export.csv"
)


def test_find_latest_screener_export(tmp_path: Path) -> None:
    assert find_latest_screener_export(tmp_path) is None
    older = tmp_path / "a.csv"
    newer = tmp_path / "b.csv"
    older.write_text("Name,BSE Code\nX,1\n", encoding="utf-8")
    newer.write_text("Name,BSE Code\nY,2\n", encoding="utf-8")
    assert find_latest_screener_export(tmp_path) == newer


def test_import_screener_export_fills_snapshots(session) -> None:
    result = import_screener_export(session, FIXTURE)
    session.commit()
    assert result.rows_read == 1
    assert result.valuation_upserts == 1
    assert result.fund_upserts == 1
    assert result.annual_upserts == 1
    assert "527001" in result.bse_codes

    val = session.scalar(
        select(ValuationSnapshot).where(
            ValuationSnapshot.identifier_type == "BSE_CODE",
            ValuationSnapshot.identifier == "527001",
        )
    )
    assert val is not None
    assert val.market_cap_cr is not None
    assert val.pe_ratio is not None
    assert val.provider == "screener"

    fund = session.scalar(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier_type == "BSE_CODE",
            FundamentalSnapshot.identifier == "527001",
        )
    )
    assert fund is not None
    assert fund.sales is not None
    assert fund.sales_yoy_pct is not None
    assert fund.sales_3y_cagr is not None

    annual = session.scalar(
        select(AnnualFundamentalsSnapshot).where(
            AnnualFundamentalsSnapshot.identifier_type == "BSE_CODE",
            AnnualFundamentalsSnapshot.identifier == "527001",
        )
    )
    assert annual is not None
    assert annual.roce is not None
    assert annual.roe is not None
    assert annual.provider == "screener"
