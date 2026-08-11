"""Tests for watchlist export/import and health."""

from __future__ import annotations

import json
from pathlib import Path

from pms_platform.fundamentals.import_csv import import_quarterly_fundamentals
from pms_platform.fundamentals.service import recompute_all_snapshots
from pms_platform.models import ImportBatch, Security
from pms_platform.watchlists import export_import as wi
from pms_platform.watchlists import health as wh
from pms_platform.watchlists import service as wl

FIXTURE = Path("tests/fixtures/market_data/fundamentals/quarterly_fundamentals.csv")


def test_export_import_json_roundtrip(session, import_batch: ImportBatch) -> None:
    source = wl.create_watchlist(session, name="Source")
    session.commit()
    wl.add_member(session, source.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    payload = wi.export_watchlist_json(session, source.watchlist_id)
    result = wi.import_watchlist_json(session, payload, create_name="Copy")
    session.commit()

    assert result.watchlist_name == "Copy"
    assert result.members_added == 1
    copy_members = wl.list_members(session, result.watchlist_id)
    assert len(copy_members) == 1
    assert copy_members[0].display_name == "Heritage"


def test_health_report_counts(session, import_batch: ImportBatch) -> None:
    sec = Security(
        security_id="SEC014",
        portfolio_name="Heritage",
        current_nse_symbol="HERITGFOOD",
        bse_code="524470",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(sec)
    watchlist = wl.create_watchlist(session, name="Health")
    session.commit()
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    import_quarterly_fundamentals(session, FIXTURE)
    recompute_all_snapshots(session)
    session.commit()

    row = wh.build_watchlist_health(session, watchlist.watchlist_id)
    assert row.member_count == 1
    assert row.resolved_count == 1
    assert row.with_fundamentals_count == 1

    report = wh.build_all_watchlists_health(session)
    assert report.watchlist_count >= 1
    assert report.fundamentals_provider in {"manual", "screener", "yahoo", "xbrl"}


def test_export_csv_contains_header(session) -> None:
    watchlist = wl.create_watchlist(session, name="CSV")
    session.commit()
    csv_text = wi.export_watchlist_csv(session, watchlist.watchlist_id)
    assert "display_name" in csv_text
    assert "nse_symbol" in csv_text
