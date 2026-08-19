"""Unit tests for watchlist CRUD."""

from __future__ import annotations

import pytest

from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.watchlists import service as wl


def test_create_first_watchlist_is_default(session, sample_security) -> None:
    row = wl.create_watchlist(session, name="Ideas")
    session.commit()
    assert row.is_default is True
    assert row.name == "Ideas"


def test_add_and_remove_member(session, sample_security) -> None:
    watchlist = wl.create_watchlist(session, name="Core")
    session.commit()

    member = wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(portfolio_name="TestCo"),
    )
    session.commit()
    assert member.security_id == "SEC999"
    assert member.resolution_status == "RESOLVED"

    members = wl.list_members(session, watchlist.watchlist_id)
    assert len(members) == 1

    wl.remove_member(session, watchlist.watchlist_id, member.member_id)
    session.commit()
    assert wl.member_count(session, watchlist.watchlist_id) == 0


def test_duplicate_member_raises(session, sample_security) -> None:
    watchlist = wl.create_watchlist(session, name="Dup")
    session.commit()
    wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(security_id="SEC999"),
    )
    session.commit()
    with pytest.raises(wl.DuplicateMemberError):
        wl.add_member(
            session,
            watchlist.watchlist_id,
            wl.MemberInput(portfolio_name="TestCo"),
        )


def test_delete_watchlist_cascades_members(session, sample_security) -> None:
    from sqlalchemy import func, select

    first = wl.create_watchlist(session, name="Keep")
    second = wl.create_watchlist(session, name="Drop", make_default=False)
    session.commit()
    wl.add_member(session, second.watchlist_id, wl.MemberInput(security_id="SEC999"))
    session.commit()

    wl.delete_watchlist(session, second.watchlist_id, confirm=True)
    session.commit()

    assert session.get(Watchlist, second.watchlist_id) is None
    assert session.scalar(select(func.count()).select_from(WatchlistMember)) == 0
    remaining = wl.get_watchlist(session, first.watchlist_id)
    assert remaining.is_default is True


def test_cannot_delete_default_while_others_exist(session, sample_security) -> None:
    default = wl.create_watchlist(session, name="Default")
    wl.create_watchlist(session, name="Other", make_default=False)
    session.commit()
    with pytest.raises(wl.WatchlistDeleteError):
        wl.delete_watchlist(session, default.watchlist_id, confirm=True)


def test_search_securities(session, sample_security) -> None:
    hits = wl.search_securities(session, "test")
    assert len(hits) == 1
    assert hits[0].portfolio_name == "TestCo"


def test_combined_search_skips_yahoo_by_default(session, sample_security) -> None:
    from unittest.mock import patch

    with patch("pms_platform.market_data.yahoo_finance.YahooFinanceClient") as client:
        hits = wl.search_securities_combined(session, "test")
        client.assert_not_called()
    assert len(hits) == 1
    assert hits[0].source == "MASTER"


def test_parse_and_bulk_add_pending(session, sample_security) -> None:
    watchlist = wl.create_watchlist(session, name="Paste")
    names = wl.parse_pasted_names("TestCo\nUnknown Co\nTestCo,  HERITGFOOD")
    assert names == ["TestCo", "Unknown Co", "HERITGFOOD"]
    result = wl.add_members_by_names(session, watchlist.watchlist_id, names)
    session.commit()
    assert result.added == 3
    assert result.pending == 2
    assert result.skipped == 0
    members = wl.list_members(session, watchlist.watchlist_id)
    by_name = {m.display_name: m for m in members}
    assert by_name["TestCo"].security_id == "SEC999"
    assert by_name["Unknown Co"].resolution_status == "PENDING"
    again = wl.add_members_by_names(session, watchlist.watchlist_id, ["TestCo"])
    assert again.skipped == 1
