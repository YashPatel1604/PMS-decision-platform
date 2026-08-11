"""Tests for watchlist SAST / insider alerts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from pms_platform.market_data.bse_corporate_disclosures import CorporateDisclosureRow
from pms_platform.models import ImportBatch, Security, WatchlistAlert
from pms_platform.watchlists import alerts as wa
from pms_platform.watchlists import service as wl


def _heritage_sast_row() -> CorporateDisclosureRow:
    return CorporateDisclosureRow(
        kind="sast",
        disclosure_date=date(2026, 8, 5),
        bse_code="524470",
        company_name="Heritage Foods Ltd",
        person_name="Promoter Holdco",
        category="Promoter",
        transaction_type="Acquisition",
        quantity=Decimal("10000"),
        value=None,
        pct_pre=Decimal("50"),
        pct_post=Decimal("51"),
        mode="Market",
        regulation="29(1)",
        isin="INE978A01027",
    )


def _other_sast_row() -> CorporateDisclosureRow:
    return CorporateDisclosureRow(
        kind="sast",
        disclosure_date=date(2026, 8, 5),
        bse_code="999999",
        company_name="Other Co",
        person_name="Someone",
        category="Promoter",
        transaction_type="Sale",
        quantity=Decimal("100"),
        value=None,
        pct_pre=Decimal("10"),
        pct_post=Decimal("9"),
        mode="Market",
        regulation="29(2)",
    )


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


@patch("pms_platform.watchlists.alerts.fetch_disclosures_for_codes")
def test_poll_creates_alert_for_watchlist_member(
    mock_fetch,
    session,
    heritage_security,
) -> None:
    mock_fetch.side_effect = [
        [_heritage_sast_row()],
        [],
    ]
    watchlist = wl.create_watchlist(session, name="Alerts")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    result = wa.poll_watchlist_alerts(session, watchlist.watchlist_id)
    session.commit()

    assert result.inserted == 1
    assert result.matched == 1
    alerts = wa.list_alerts(session, watchlist.watchlist_id)
    assert len(alerts) == 1
    assert alerts[0].bse_code == "524470"
    assert alerts[0].kind == "sast"


@patch("pms_platform.watchlists.alerts.fetch_disclosures_for_codes")
def test_poll_scoped_to_watchlist_bse_codes(mock_fetch, session, heritage_security) -> None:
    mock_fetch.side_effect = [
        [_other_sast_row()],
        [],
    ]
    watchlist = wl.create_watchlist(session, name="Empty match")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    result = wa.poll_watchlist_alerts(session, watchlist.watchlist_id)
    session.commit()

    assert result.inserted == 0
    assert session.scalar(select(func.count()).select_from(WatchlistAlert)) == 0


@patch("pms_platform.watchlists.alerts.fetch_disclosures_for_codes")
def test_poll_is_idempotent(mock_fetch, session, heritage_security) -> None:
    mock_fetch.side_effect = [
        [_heritage_sast_row()],
        [],
        [_heritage_sast_row()],
        [],
    ]
    watchlist = wl.create_watchlist(session, name="Dedupe")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()

    first = wa.poll_watchlist_alerts(session, watchlist.watchlist_id)
    session.commit()
    second = wa.poll_watchlist_alerts(session, watchlist.watchlist_id)
    session.commit()

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped == 1
    assert session.scalar(select(func.count()).select_from(WatchlistAlert)) == 1


@patch("pms_platform.watchlists.alerts.fetch_disclosures_for_codes")
def test_acknowledge_alert(mock_fetch, session, heritage_security) -> None:
    mock_fetch.side_effect = [[_heritage_sast_row()], []]
    watchlist = wl.create_watchlist(session, name="Ack")
    wl.add_member(session, watchlist.watchlist_id, wl.MemberInput(portfolio_name="Heritage"))
    session.commit()
    wa.poll_watchlist_alerts(session, watchlist.watchlist_id)
    session.commit()
    alert = wa.list_alerts(session, watchlist.watchlist_id)[0]

    updated = wa.acknowledge_alert(session, watchlist.watchlist_id, alert.alert_id)
    session.commit()

    assert updated.acknowledged is True
    assert updated.acknowledged_at is not None
    assert wa.unacknowledged_count(session) == 0
