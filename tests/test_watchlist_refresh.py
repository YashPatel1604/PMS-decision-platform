"""Tests for watchlist refresh orchestration and mutex."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pms_platform.models.watchlist_refresh_lock import WatchlistRefreshLock
from pms_platform.watchlists import refresh as wr
from pms_platform.watchlists import service as wl


@patch("pms_platform.watchlists.refresh.wa.poll_watchlist_alerts")
@patch("pms_platform.watchlists.refresh.sync_fundamentals")
def test_refresh_watchlist_orchestrates_steps(
    mock_fundamentals,
    mock_poll,
    session,
) -> None:
    from pms_platform.fundamentals.service import FundamentalsSyncResult

    mock_fundamentals.return_value = FundamentalsSyncResult(
        import_result=None,
        yahoo_result=None,
        bse_result=None,
        snapshots_written=10,
        identifiers_processed=5,
    )
    mock_poll.return_value = type("R", (), {"inserted": 2, "skipped": 0, "matched": 2})()

    watchlist = wl.create_watchlist(session, name="Refresh")
    session.commit()

    result = wr.refresh_watchlist(session, watchlist.watchlist_id, include_fundamentals=True)
    session.commit()

    assert result.watchlist_name == "Refresh"
    assert result.fundamentals is not None
    assert result.fundamentals.snapshots_written == 10
    assert result.alerts.inserted == 2
    mock_fundamentals.assert_called_once()
    mock_poll.assert_called_once()


@patch("pms_platform.watchlists.refresh.wa.poll_watchlist_alerts")
@patch("pms_platform.watchlists.refresh.wl.resolve_stale_members")
def test_refresh_mutex_rejects_concurrent(_mock_resolve, _mock_poll, session) -> None:
    watchlist = wl.create_watchlist(session, name="Locked")
    session.commit()

    wr.acquire_refresh_lock(session, watchlist.watchlist_id)
    session.commit()

    with pytest.raises(wr.WatchlistRefreshInProgressError):
        wr.refresh_watchlist(session, watchlist.watchlist_id, include_fundamentals=False)


def test_expired_lock_is_cleared(session) -> None:
    from datetime import datetime, timedelta, timezone

    watchlist = wl.create_watchlist(session, name="Expire")
    session.commit()
    session.add(
        WatchlistRefreshLock(
            watchlist_id=watchlist.watchlist_id,
            locked_at=datetime.now(timezone.utc) - timedelta(hours=1),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    session.commit()

    wr.acquire_refresh_lock(session, watchlist.watchlist_id)
    session.commit()
    assert session.get(WatchlistRefreshLock, watchlist.watchlist_id) is not None
