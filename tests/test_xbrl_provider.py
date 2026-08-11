"""Tests for BSE fundamentals provider (xbrl)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from pms_platform.fundamentals.providers.xbrl import XbrlFundamentalsProvider
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.market_data.bse_financial_results import parse_results_snapshot
from pms_platform.models import FundamentalSnapshot, ImportBatch, Security
from pms_platform.models.company_fundamentals_quarterly import CompanyFundamentalsQuarterly
from pms_platform.watchlists import service as wl

FIXTURE = Path("tests/fixtures/market_data/bse/results_snapshot.json")


def _mock_snapshot(bse_code: str):
    payload = json.loads(FIXTURE.read_text())
    return parse_results_snapshot(bse_code, payload)


def test_xbrl_provider_imports_bse_quarters(session, import_batch: ImportBatch) -> None:
  security = Security(
      security_id="SEC014",
      portfolio_name="Heritage",
      current_nse_symbol="HERITGFOOD",
      bse_code="524470",
      import_batch_id=import_batch.import_batch_id,
  )
  session.add(security)
  session.flush()

  with patch(
      "pms_platform.fundamentals.providers.xbrl.fetch_bse_quarterly_results_with_history",
      side_effect=lambda code, **kwargs: _mock_snapshot(code),
  ):
      result = XbrlFundamentalsProvider(request_delay_sec=0).import_data(
          session,
          bse_codes=["524470"],
      )

  assert result.inserted == 2
  assert result.invalid == 0

  rows = session.scalars(
      select(CompanyFundamentalsQuarterly).where(
          CompanyFundamentalsQuarterly.identifier == "524470"
      )
  ).all()
  assert len(rows) == 2
  assert rows[0].provider == "xbrl"
  assert rows[0].sales == Decimal("2650.00")


def test_xbrl_provider_populates_watchlist_screener(session, import_batch: ImportBatch) -> None:
    security = Security(
        security_id="SEC050",
        portfolio_name="Ashapura",
        current_nse_symbol="ASHAPURMIN",
        bse_code="527001",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(security)
    session.flush()

    watchlist = wl.create_watchlist(session, name="Phase C")
    wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(portfolio_name="Ashapura", bse_code="527001", nse_symbol="ASHAPURMIN"),
    )
    session.commit()

    with patch(
        "pms_platform.fundamentals.providers.xbrl.fetch_bse_quarterly_results_with_history",
        side_effect=lambda code, **kwargs: _mock_snapshot(code),
    ):
        XbrlFundamentalsProvider(request_delay_sec=0).import_data(session, bse_codes=["527001"])

    recompute_all_snapshots(session)
    session.commit()

    snapshots = session.scalars(
        select(FundamentalSnapshot).where(
            FundamentalSnapshot.identifier_type == "BSE_CODE",
            FundamentalSnapshot.identifier == "527001",
        )
    ).all()
    assert len(snapshots) == 2
    latest = max(snapshots, key=lambda row: row.period_end_date)
    assert latest.sales == Decimal("2883.00")
    assert latest.opm == Decimal("27.89")
