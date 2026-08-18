"""Tests for materialized watchlist screener cache."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from pms_platform.fundamentals.import_csv import import_quarterly_fundamentals
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.models import WatchlistMemberMetrics
from pms_platform.watchlists import metrics_cache as mc
from pms_platform.watchlists import screen as scr
from pms_platform.watchlists import service as wl

FIXTURE = Path("tests/fixtures/market_data/fundamentals/quarterly_fundamentals.csv")


@pytest.fixture
def heritage_security(session, import_batch):
    from pms_platform.models import Security

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


def test_rebuild_and_load_cached_screen(session, heritage_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    watchlist = wl.create_watchlist(session, name="Cache")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    written = mc.rebuild_watchlist_metrics(session, watchlist.watchlist_id)
    session.commit()
    assert written == 1

    cached = mc.load_cached_screen_rows(
        session,
        watchlist.watchlist_id,
        column_keys=("sales", "sales_yoy_pct"),
    )
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].metrics["sales_yoy_pct"] == Decimal("25.0000")

    screen = scr.build_watchlist_screen(
        session,
        watchlist.watchlist_id,
        columns="sales,sales_yoy_pct",
    )
    assert screen[0].metrics["sales_yoy_pct"] == Decimal("25.0000")

    row = session.scalar(
        select(WatchlistMemberMetrics).where(
            WatchlistMemberMetrics.watchlist_id == watchlist.watchlist_id
        )
    )
    assert row is not None
    assert row.has_fundamentals is True


def test_cache_miss_falls_back_to_snapshots(session, heritage_security) -> None:
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    watchlist = wl.create_watchlist(session, name="Fallback")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    rows = scr.build_watchlist_screen(session, watchlist.watchlist_id)
    assert rows[0].has_fundamentals is True
