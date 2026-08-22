"""Tests for watchlist data coverage audit."""

from __future__ import annotations

from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.watchlists.audit import audit_watchlist_data, format_audit_report


def test_audit_empty_watchlist(session) -> None:
    wl = Watchlist(name="Empty", is_default=False)
    session.add(wl)
    session.flush()

    report = audit_watchlist_data(session, watchlist_id=wl.watchlist_id)
    assert report.total_members == 0
    assert report.overall_coverage_pct == 0.0
    text = format_audit_report(report)
    assert "total=0" in text


def test_audit_unresolved_member_gets_reason(session, sample_security) -> None:
    wl = Watchlist(name="Test", is_default=False)
    session.add(wl)
    session.flush()
    session.add(
        WatchlistMember(
            watchlist_id=wl.watchlist_id,
            display_name="Unresolved Co",
            bse_code="500325",
            nse_symbol="RELIANCE",
            security_id=sample_security.security_id,
            resolution_status="PENDING",
        )
    )
    session.flush()

    report = audit_watchlist_data(session, watchlist_id=wl.watchlist_id)
    assert report.unresolved_members == 1
    assert report.resolved_members == 0
