"""Tests for watchlist canonical identity linking."""

from __future__ import annotations

from pms_platform.models import ImportBatch, Security
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import identity_link as il


def test_link_existing_master_by_bse(session, import_batch: ImportBatch) -> None:
    sec = Security(
        security_id="SEC900",
        portfolio_name="FSL",
        bse_code="532809",
        current_nse_symbol="FSL",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(sec)
    member = WatchlistMember(
        watchlist_id=1,
        display_name="Firstsource",
        bse_code="532809",
        resolution_status="EXCHANGE_RESOLVED",
        resolution_source="BSE",
    )
    session.add(member)
    session.flush()

    result = il.link_watchlist_member(session, member)
    session.flush()

    assert result.linkage_status == "CANONICALLY_LINKED"
    assert member.security_id == "SEC900"
    assert member.resolution_status == "RESOLVED"


def test_unsupported_member_classified(session) -> None:
    member = WatchlistMember(
        watchlist_id=2,
        display_name="Dummy",
        resolution_status="FAILED",
    )
    session.add(member)
    session.flush()

    result = il.link_watchlist_member(session, member)
    assert result.linkage_status == "UNSUPPORTED"
    assert member.resolution_status == "UNSUPPORTED"
    assert member.security_id is None
