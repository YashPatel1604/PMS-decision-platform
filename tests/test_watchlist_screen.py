"""Tests for watchlist fundamentals screener."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from pms_platform.fundamentals.import_csv import import_quarterly_fundamentals
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.models import FundamentalSnapshot, ImportBatch, Security
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl

FIXTURE = Path("tests/fixtures/market_data/fundamentals/quarterly_fundamentals.csv")


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


def test_sort_sales_yoy_desc_nulls_last(session, heritage_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    watchlist = wl.create_watchlist(session, name="Screen")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(display_name="No Data Co", nse_symbol="NODATA"),
    )
    session.commit()

    rows = scr.build_watchlist_screen(
        session,
        watchlist.watchlist_id,
        sort="sales_yoy_pct:desc",
    )
    assert len(rows) == 2
    assert rows[0].display_name == "Heritage"
    assert rows[0].metrics["sales_yoy_pct"] == Decimal("25.0000")
    assert rows[1].has_fundamentals is False


def test_fundamentals_stale_flag(session, heritage_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    snapshots = session.scalars(
        select(FundamentalSnapshot).where(FundamentalSnapshot.identifier == "Heritage")
    ).all()
    assert snapshots
    stale_at = datetime.now(timezone.utc) - timedelta(days=120)
    for snapshot in snapshots:
        snapshot.retrieved_at = stale_at
    session.flush()
    watchlist = wl.create_watchlist(session, name="Stale")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    rows = scr.build_watchlist_screen(session, watchlist.watchlist_id)
    assert rows[0].fundamentals_stale is True


def test_screen_csv_export(session, heritage_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    watchlist = wl.create_watchlist(session, name="Export")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    rows = scr.build_watchlist_screen(
        session,
        watchlist.watchlist_id,
        columns="sales,sales_yoy_pct",
    )
    csv_text = scr.screen_rows_to_csv(rows, ("sales", "sales_yoy_pct"))
    assert "Heritage" in csv_text
    assert "Sales YoY %" in csv_text
    assert "25.0000" in csv_text
