"""Tests for historical identity aliases."""

from __future__ import annotations

from pms_platform.models import ImportBatch, Security
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import identity_aliases as ia
from pms_platform.watchlists import identity_link as il


def test_lookup_watchlist_alias_seed(session) -> None:
    match = ia.lookup_watchlist_alias(session, "HBL Power")
    assert match is not None
    assert match.bse_code == "517271"
    assert match.nse_symbol == "HBLENGINE"
    assert match.relationship_type == "RENAMED"


def test_link_renamed_member_via_alias(session, import_batch: ImportBatch) -> None:
    ia.bootstrap_identity_aliases(session)
    session.flush()
    member = WatchlistMember(
        watchlist_id=2,
        display_name="Sequent",
        resolution_status="UNSUPPORTED",
        resolution_note="DELISTED",
    )
    session.add(member)
    session.flush()
    result = il.link_watchlist_member(session, member)
    session.flush()
    assert result.linkage_status == "CANONICALLY_LINKED"
    assert member.security_id is not None
    assert member.resolution_status == "RESOLVED"
    assert "RENAMED" in (member.resolution_note or "")


def test_positive_unsupported_dummy(session) -> None:
    member = WatchlistMember(
        watchlist_id=2,
        display_name="Dummy",
        resolution_status="FAILED",
    )
    session.add(member)
    session.flush()
    result = il.link_watchlist_member(session, member)
    assert result.linkage_status == "UNSUPPORTED"
    assert member.resolution_note == "DUMMY"


def test_all_identifiers_includes_alias_symbols(session, import_batch: ImportBatch) -> None:
    ia.bootstrap_identity_aliases(session)
    sec = session.scalar(
        __import__("sqlalchemy").select(Security).where(Security.bse_code == "517271")
    )
    assert sec is not None
    ids = ia.all_identifiers_for_security(session, sec.security_id)
    types = {t for t, _ in ids}
    assert "NSE_SYMBOL" in types
    assert "BSE_CODE" in types
