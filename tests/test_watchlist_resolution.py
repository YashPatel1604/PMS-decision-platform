"""Tests for watchlist symbol resolution pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pms_platform.market_data.yahoo_finance import YahooSearchHit
from pms_platform.models import ImportBatch, Security
from pms_platform.models.watchlist import WatchlistMember
from pms_platform.watchlists import resolution as res
from pms_platform.watchlists import service as wl


@pytest.fixture
def heritage_security(session, import_batch: ImportBatch) -> Security:
    row = Security(
        security_id="SEC014",
        portfolio_name="Heritage",
        current_nse_symbol="HERITGFOOD",
        bse_code="524470",
        isin="INE978A01027",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


@pytest.fixture
def mosl_security(session, import_batch: ImportBatch) -> Security:
    row = Security(
        security_id="SEC040",
        portfolio_name="MOSL",
        current_nse_symbol="MOTILALOFS",
        bse_code="532167",
        import_batch_id=import_batch.import_batch_id,
    )
    session.add(row)
    session.flush()
    return row


def test_resolve_heritage_via_master(session, heritage_security) -> None:
    result = res.resolve_identifiers(session, display_name="Heritage")
    assert result.status == "RESOLVED"
    assert result.source == "MASTER"
    assert result.security_id == "SEC014"
    assert result.nse_symbol == "HERITGFOOD"


def test_resolve_mosl_via_nse_symbol(session, mosl_security) -> None:
    result = res.resolve_identifiers(session, display_name="MOSL", nse_symbol="MOTILALOFS")
    assert result.status == "RESOLVED"
    assert result.source == "MASTER"
    assert result.security_id == "SEC040"


@patch(
    "pms_platform.watchlists.resolution.resolve_bse_code",
    side_effect=[None, "543999"],
)
@patch("pms_platform.watchlists.resolution.YahooFinanceClient")
def test_resolve_unknown_via_yahoo(mock_client_cls, _mock_bse, session) -> None:
    mock_client_cls.return_value.search.return_value = [
        YahooSearchHit(
            symbol="SMALLCO",
            name="Small Co Ltd",
            exchange="NSE",
            yahoo_ticker="SMALLCO.NS",
        )
    ]
    result = res.resolve_identifiers(session, display_name="Small Co Ltd")
    assert result.status == "EXCHANGE_RESOLVED"
    assert result.source == "YAHOO"
    assert result.nse_symbol == "SMALLCO"
    assert result.bse_code == "543999"


@patch("pms_platform.watchlists.resolution.YahooFinanceClient")
def test_resolve_unknown_fails_when_no_yahoo(mock_client_cls, session) -> None:
    mock_client_cls.return_value.search.return_value = []
    result = res.resolve_identifiers(session, display_name="Totally Unknown XYZ")
    assert result.status == "FAILED"
    assert result.source is None


def test_is_resolution_stale(session) -> None:
    member = WatchlistMember(
        watchlist_id=1,
        display_name="X",
        resolution_status="RESOLVED",
        resolved_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    assert res.is_resolution_stale(member) is True

    member.resolved_at = datetime.now(timezone.utc)
    assert res.is_resolution_stale(member) is False

    member.resolution_status = "PENDING"
    assert res.is_resolution_stale(member) is False


def test_manual_symbol_fix_resolves(session) -> None:
    watchlist = wl.create_watchlist(session, name="Fix")
    session.commit()
    member = wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(display_name="Manual Only Co"),
    )
    session.commit()
    assert member.resolution_status in {"PENDING", "FAILED", "RESOLVED"}

    updated = wl.update_member_symbols(
        session,
        watchlist.watchlist_id,
        member.member_id,
        nse_symbol="MANUAL",
        bse_code="123456",
    )
    session.commit()
    assert updated.resolution_status == "EXCHANGE_RESOLVED"
    assert updated.resolution_source == "MANUAL"
    assert updated.nse_symbol == "MANUAL"
    assert updated.bse_code == "123456"
