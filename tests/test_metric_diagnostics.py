"""Tests for v2.0 watchlist metrics diagnostics."""

from __future__ import annotations

from decimal import Decimal

from pms_platform.fundamentals.catalog import WATCHLIST_METRICS_VERSION
from pms_platform.models.watchlist import Watchlist, WatchlistMember
from pms_platform.watchlists.member_context import load_member_snapshot_context
from pms_platform.watchlists.metric_diagnostics import MissingReason, build_member_diagnostics


def test_build_member_diagnostics_unresolved(session, sample_security) -> None:
    wl = Watchlist(name="Diag", is_default=False)
    session.add(wl)
    session.flush()
    member = WatchlistMember(
        watchlist_id=wl.watchlist_id,
        display_name="Pending Co",
        bse_code="500325",
        nse_symbol="RELIANCE",
        resolution_status="PENDING",
    )
    session.add(member)
    session.flush()
    ctx = load_member_snapshot_context(session, member)
    diag = build_member_diagnostics(
        session,
        member,
        {"sales": None},
        ctx,
        computation_version=WATCHLIST_METRICS_VERSION,
        metric_keys=("sales",),
    )
    assert diag["missing_reasons"]["sales"] == MissingReason.UNRESOLVED_SECURITY.value
    assert "provenance" in diag


def test_build_member_diagnostics_with_value(session, sample_security) -> None:
    wl = Watchlist(name="Diag2", is_default=False)
    session.add(wl)
    session.flush()
    member = WatchlistMember(
        watchlist_id=wl.watchlist_id,
        display_name="Resolved Co",
        bse_code="500325",
        nse_symbol="RELIANCE",
        security_id=sample_security.security_id,
        resolution_status="RESOLVED",
    )
    session.add(member)
    session.flush()
    ctx = load_member_snapshot_context(session, member)
    diag = build_member_diagnostics(
        session,
        member,
        {"sales": Decimal("100")},
        ctx,
        computation_version=WATCHLIST_METRICS_VERSION,
        metric_keys=("sales",),
    )
    assert "sales" not in diag["missing_reasons"]
