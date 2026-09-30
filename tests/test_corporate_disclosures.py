"""Unit tests for BSE SAST / Insider disclosure normalization."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from pms_platform.market_data.bse_corporate_disclosures import (
    fetch_corporate_disclosures,
    normalize_insider_row,
    normalize_sast_row,
)
from pms_platform.market_data.insider_store import _scrip_code, sync_insider_days
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay
from pms_platform.watchlists import service as wl


def test_nse_sast_row_normalizes_when_bse_blocked() -> None:
    from pms_platform.market_data.bse_corporate_disclosures import _nse_sast_as_bse_row

    shaped = _nse_sast_as_bse_row(
        {
            "company": "PVR INOX Limited",
            "symbol": "PVRINOX",
            "acquirerName": "Selena Bijli",
            "acquirerDate": "24-SEP-2026 to 24-SEP-2026",
            "acqSaleType": "Sale",
            "noOfShareSale": "502200",
            "noOfShareAcq": None,
            "promoterType": "Y",
            "totAftShare": "24.54",
            "regType": "Reg29(2)",
            "acquisitionMode": "Others",
        }
    )
    with patch(
        "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
        return_value=None,
    ):
        row = normalize_sast_row(shaped)
    assert row is not None
    assert row.bse_code == "PVRINOX"
    assert row.disclosure_date == date(2026, 9, 24)
    assert row.quantity == Decimal("502200")
    assert row.person_name == "Selena Bijli"
    assert row.category == "Promoter"


def test_normalize_sast_row_resolves_isin() -> None:
    raw = {
        "ScripCode": None,
        "ComName": "APOLLO PIPES LIMITED EQ",
        "ProISIN": "INE126J01016",
        "PromName": "S Gupta Holding Private Limited",
        "PreHold": 2175014.0,
        "PerPreHold": 4.94,
        "QTYTrans": 403089,
        "PerQTY": 0.92,
        "PostHold": 2578103.0,
        "PerPostHold": 5.85,
        "DATETrans": "2026-08-05T00:00:00",
        "TransType": "Acquisition of shares - market",
        "Promoter_NonPromoter": "Promoter",
        "reg29_1_2": "29(1)",
        "transactiondisplay": "2026-08-06",
    }
    with patch(
        "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
        return_value="542534",
    ):
        row = normalize_sast_row(raw)
    assert row is not None
    assert row.kind == "sast"
    assert row.bse_code == "542534"
    assert row.disclosure_date == date(2026, 8, 5)
    assert row.quantity == Decimal("403089")
    assert row.regulation == "29(1)"


def test_nse_insider_row_normalizes() -> None:
    from pms_platform.market_data.bse_corporate_disclosures import _nse_insider_as_bse_row

    shaped = _nse_insider_as_bse_row(
        {
            "symbol": "RELIANCE",
            "company": "Reliance Industries Limited",
            "acqName": "BALANADU NARAYAN",
            "personCategory": "Other",
            "tdpTransactionType": "Sell",
            "secAcq": "2320",
            "secVal": "3294168",
            "befAcqSharesPer": "0",
            "afterAcqSharesPer": "0",
            "date": "18-Feb-2026 19:06",
            "acqMode": "Off Market",
            "did": "563850",
            "remarks": "-",
        }
    )
    row = normalize_insider_row(shaped)
    assert row is not None
    assert row.bse_code == "RELIANCE"
    assert row.disclosure_date == date(2026, 2, 18)
    assert row.quantity == Decimal("2320")
    assert row.person_name == "BALANADU NARAYAN"
    assert row.transaction_type == "Sell"


def test_normalize_insider_row() -> None:
    raw = {
        "Fld_ScripCode": 544444,
        "Companyname": "Glen Industries Ltd",
        "Fld_PromoterName": "Lalit Agrawal(HUF)",
        "Fld_PersonCatgName": "Promoter Group",
        "Fld_TransactionType": "Acquisition",
        "Fld_SecurityNo": 44400,
        "Fld_SecurityValue": "4966584.00",
        "Fld_PercentofShareholdingPre": "0.78",
        "Fld_PercentofShareholdingPost": "0.96",
        "Fld_StampDate": "2026-08-06T00:00:00",
        "ModeOfAquisation": "Market Purchase",
    }
    row = normalize_insider_row(raw)
    assert row is not None
    assert row.kind == "insider"
    assert row.bse_code == "544444"
    assert row.disclosure_date == date(2026, 8, 6)
    assert row.value == Decimal("4966584.00")
    assert row.mode == "Market Purchase"


def test_normalize_insider_row_requires_bse_scrip_code() -> None:
    raw = {
        "Companyname": "Corona Remedies Ltd",
        "Fld_PromoterName": "Someone",
        "Fld_StampDate": "2026-08-19T00:00:00",
    }
    assert normalize_insider_row(raw) is None


def _insider_raw(day: date, count: int) -> list[dict]:
    return [
        {
            "Fld_ID": int(day.strftime("%Y%m%d")) * 100 + i,
            "Fld_ScripCode": 500325,
            "Companyname": "Test Co",
            "Fld_PromoterName": f"Person {i}",
            "Fld_PersonCatgName": "Promoter",
            "Fld_TransactionType": "Acquisition",
            "Fld_SecurityNo": 100,
            "Fld_StampDate": f"{day.isoformat()}T00:00:00",
        }
        for i in range(count)
    ]


def _fake_bse_insider(from_date: date, to_date: date) -> list[dict]:
    """Range search only returns the newest day (BSE 25-row cap)."""
    if from_date != to_date:
        return _insider_raw(to_date, 25)
    if from_date == date(2026, 8, 11):
        return _insider_raw(from_date, 3)
    if from_date == date(2026, 8, 18):
        return _insider_raw(from_date, 25)
    return []


def _range_days(start: date, end: date) -> list[date]:
    from datetime import timedelta

    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def test_insider_store_fetches_one_day_at_a_time(session) -> None:
    calls: list[tuple[date, date, str]] = []

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        calls.append((from_date, to_date, scrip_code))
        if scrip_code:
            return []
        return _fake_bse_insider(from_date, to_date)

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset(),
        ),
    ):
        fetched = sync_insider_days(
            session,
            date(2026, 8, 11),
            date(2026, 8, 18),
            today=date(2026, 8, 18),
        )
        session.commit()

    assert fetched == 8
    assert all(start == end and not code for start, end, code in calls)
    older = session.get(InsiderDisclosureDay, date(2026, 8, 11))
    assert older is not None
    assert older.row_count == 3
    assert older.truncated is False
    today_row = session.get(InsiderDisclosureDay, date(2026, 8, 18))
    assert today_row is not None
    assert today_row.row_count == 25
    assert today_row.truncated is True

    calls.clear()
    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset(),
        ),
    ):
        fetched_again = sync_insider_days(
            session,
            date(2026, 8, 11),
            date(2026, 8, 18),
            today=date(2026, 8, 18),
        )
    assert fetched_again == 8
    assert calls == [(day, day, "") for day in _range_days(date(2026, 8, 11), date(2026, 8, 18))]


def test_insider_store_merges_watchlist_scrips_when_day_capped(session) -> None:
    watchlist = wl.create_watchlist(session, name="Core")
    wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(display_name="HDFC Bank", bse_code="500570"),
    )
    session.commit()

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        if scrip_code == "500570":
            return [
                {
                    "Fld_ID": 888001,
                    "Fld_ScripCode": 500570,
                    "Companyname": "HDFC Bank",
                    "Fld_PromoterName": "Someone",
                    "Fld_PersonCatgName": "Promoter",
                    "Fld_TransactionType": "Acquisition",
                    "Fld_SecurityNo": 50,
                    "Fld_StampDate": "2026-08-18T00:00:00",
                }
            ]
        return _fake_bse_insider(from_date, to_date)

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"500570"}),
        ),
    ):
        sync_insider_days(
            session,
            date(2026, 8, 18),
            date(2026, 8, 18),
            today=date(2026, 8, 18),
        )
        session.commit()

    stored = session.get(InsiderDisclosureDay, date(2026, 8, 18))
    assert stored is not None
    assert stored.row_count == 26
    assert stored.truncated is False
    codes = {str(row.get("Fld_ScripCode")) for row in stored.rows}
    assert "500570" in codes
    assert "500325" in codes


def test_insider_store_backfills_historical_truncated_day(session) -> None:
    session.add(
        InsiderDisclosureDay(
            disclosure_date=date(2026, 8, 11),
            rows=_insider_raw(date(2026, 8, 11), 25),
            row_count=25,
            truncated=True,
            fetched_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )
    )
    watchlist = wl.create_watchlist(session, name="Core")
    wl.add_member(
        session,
        watchlist.watchlist_id,
        wl.MemberInput(display_name="HDFC Bank", bse_code="500570"),
    )
    session.commit()

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        if scrip_code == "500570":
            return [
                {
                    "Fld_ID": 111001,
                    "Fld_ScripCode": 500570,
                    "Companyname": "HDFC Bank",
                    "Fld_StampDate": "2026-08-11T00:00:00",
                }
            ]
        return _insider_raw(from_date, 25)

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"500570"}),
        ),
    ):
        fetched = sync_insider_days(
            session,
            date(2026, 8, 11),
            date(2026, 8, 11),
            today=date(2026, 8, 30),
        )
        session.commit()

    assert fetched == 1
    stored = session.get(InsiderDisclosureDay, date(2026, 8, 11))
    assert stored is not None
    assert stored.row_count == 26
    assert stored.truncated is False

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"500570"}),
        ),
    ):
            fetched_again = sync_insider_days(
                session,
                date(2026, 8, 11),
                date(2026, 8, 11),
                today=date(2026, 8, 30),
            )
    assert fetched_again == 0


def test_insider_store_refreshes_stale_recent_snapshot(session) -> None:
    """Early BSE snapshot (10 rows) must not freeze once more filings land."""
    day = date(2026, 8, 19)
    session.add(
        InsiderDisclosureDay(
            disclosure_date=day,
            rows=_insider_raw(day, 10),
            row_count=10,
            truncated=False,
            fetched_at=datetime(2026, 8, 19, 6, tzinfo=timezone.utc),
        )
    )
    session.commit()

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        if from_date == day and not scrip_code:
            return _insider_raw(day, 25)
        return []

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset(),
        ),
    ):
        fetched = sync_insider_days(
            session,
            day,
            day,
            today=date(2026, 8, 20),
        )
        session.commit()

    assert fetched == 1
    stored = session.get(InsiderDisclosureDay, day)
    assert stored is not None
    assert stored.row_count == 25
    assert stored.truncated is True


def test_insider_store_fetches_portfolio_scrip_when_market_under_cap(
    session, sample_security
) -> None:
    """Aurionpro case: market snapshot had 10 rows; portfolio filing only via per-scrip."""
    sample_security.bse_code = "532668"
    sample_security.portfolio_name = "Aurionpro"
    session.add(sample_security)
    session.commit()

    day = date(2026, 8, 19)
    calls: list[tuple[date, date, str]] = []

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        calls.append((from_date, to_date, scrip_code))
        if scrip_code == "532668":
            return [
                {
                    "Fld_ID": 532668001,
                    "Fld_ScripCode": 532668,
                    "Companyname": "Aurionpro Solutions Ltd",
                    "Fld_PromoterName": "ASHISH RAI",
                    "Fld_PersonCatgName": "KMP",
                    "Fld_TransactionType": "Acquisition",
                    "Fld_SecurityNo": 5000,
                    "Fld_StampDate": "2026-08-19T00:00:00",
                }
            ]
        if from_date == day:
            return _insider_raw(day, 25)
        return []

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"532668"}),
        ),
    ):
        sync_insider_days(session, day, day, today=date(2026, 8, 20))
        session.commit()

    assert any(code == "532668" for _, _, code in calls if code)
    stored = session.get(InsiderDisclosureDay, day)
    assert stored is not None
    assert stored.row_count == 26
    assert stored.truncated is False
    codes = {_scrip_code(row) for row in stored.rows}
    assert "532668" in codes


def test_insider_store_skips_scrip_sweep_when_market_under_cap(session) -> None:
    day = date(2026, 8, 19)
    calls: list[str] = []

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        calls.append(scrip_code)
        if scrip_code:
            raise AssertionError("scrip fetch should not run under cap")
        return _insider_raw(day, 10)

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"532668", "544644"}),
        ),
    ):
        sync_insider_days(session, day, day, today=date(2026, 8, 20))
        session.commit()

    assert calls == [""]
    stored = session.get(InsiderDisclosureDay, day)
    assert stored is not None
    assert stored.row_count == 10
    assert stored.truncated is False


def test_insider_store_fetches_large_cap_scrip_when_day_capped(session) -> None:
    """Large-cap names (e.g. Corona) must appear when market hits the 25-row cap."""
    day = date(2026, 8, 19)

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        if scrip_code == "544644":
            return [
                {
                    "Fld_ID": 544644001,
                    "Fld_ScripCode": 544644,
                    "Companyname": "Corona Remedies Ltd",
                    "Fld_PromoterName": "Apurvsinh Kirtisinh Parmar",
                    "Fld_TransactionType": "Acquisition",
                    "Fld_StampDate": "2026-08-19T00:00:00",
                }
            ]
        if from_date == to_date == day:
            return _insider_raw(day, 25)
        return []

    with (
        patch(
            "pms_platform.market_data.insider_store.fetch_insider_rows",
            side_effect=fake,
        ),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset({"544644"}),
        ),
    ):
        sync_insider_days(session, day, day, today=date(2026, 8, 20))
        session.commit()

    stored = session.get(InsiderDisclosureDay, day)
    assert stored is not None
    names = {str(r.get("Companyname")) for r in stored.rows}
    assert "Corona Remedies Ltd" in names


def test_insider_market_refresh_keeps_prior_large_cap_rows(session) -> None:
    """Page Refresh (scrip_backfill=False) must not wipe Corona already in the store."""
    day = date(2026, 8, 19)
    session.add(
        InsiderDisclosureDay(
            disclosure_date=day,
            rows=_insider_raw(day, 10)
            + [
                {
                    "Fld_ID": 544644001,
                    "Fld_ScripCode": 544644,
                    "Companyname": "Corona Remedies Ltd",
                    "Fld_PromoterName": "Apurvsinh",
                    "Fld_StampDate": "2026-08-19T00:00:00",
                }
            ],
            row_count=11,
            truncated=False,
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        )
    )
    session.commit()

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        assert not scrip_code
        return _insider_raw(day, 25)

    with patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake):
        sync_insider_days(
            session, day, day, today=date(2026, 8, 20), scrip_backfill=False
        )
        session.commit()

    stored = session.get(InsiderDisclosureDay, day)
    assert stored is not None
    assert stored.row_count == 26
    names = {str(r.get("Companyname")) for r in stored.rows}
    assert "Corona Remedies Ltd" in names


def test_flag_insider_arbitrage_pairs_buy_and_sell() -> None:
    from pms_platform.market_data.bse_corporate_disclosures import (
        CorporateDisclosureRow,
        flag_insider_arbitrage,
    )

    rows = [
        CorporateDisclosureRow(
            kind="insider",
            disclosure_date=date(2026, 8, 19),
            bse_code="500325",
            company_name="Test",
            person_name="Alice",
            category="Promoter",
            transaction_type="Acquisition",
            quantity=None,
            value=None,
            pct_pre=None,
            pct_post=None,
            mode="Market Purchase",
            regulation="PIT 7(2)",
        ),
        CorporateDisclosureRow(
            kind="insider",
            disclosure_date=date(2026, 8, 19),
            bse_code="500325",
            company_name="Test",
            person_name="Alice",
            category="Promoter",
            transaction_type="Disposal",
            quantity=None,
            value=None,
            pct_pre=None,
            pct_post=None,
            mode="Market Sale",
            regulation="PIT 7(2)",
        ),
    ]
    flagged = flag_insider_arbitrage(rows)
    assert all(r.is_arbitrage for r in flagged)


def test_insider_page_returns_all_stored_names(session, sample_security) -> None:
    sample_security.bse_code = "532668"
    sample_security.portfolio_name = "Aurionpro"
    session.add(sample_security)
    session.commit()

    day = date(2026, 8, 19)
    session.add(
        InsiderDisclosureDay(
            disclosure_date=day,
            rows=[
                {
                    "Fld_ID": 1,
                    "Fld_ScripCode": 532668,
                    "Companyname": "Aurionpro Solutions Ltd",
                    "Fld_PromoterName": "ASHISH RAI",
                    "Fld_StampDate": "2026-08-19T00:00:00",
                },
                {
                    "Fld_ID": 2,
                    "Fld_ScripCode": 544644,
                    "Companyname": "Corona Remedies Ltd",
                    "Fld_PromoterName": "Apurvsinh Kirtisinh Parmar",
                    "Fld_StampDate": "2026-08-19T00:00:00",
                },
            ],
            row_count=2,
            truncated=False,
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        )
    )
    session.commit()

    with patch(
        "pms_platform.market_data.insider_store.sync_insider_days",
        return_value=0,
    ):
        market = fetch_corporate_disclosures(
            "insider",
            session,
            as_of_date=day,
            enrich_market_cap=False,
        )

    assert len(market.rows) == 2
    assert {r.company_name for r in market.rows} == {
        "Aurionpro Solutions Ltd",
        "Corona Remedies Ltd",
    }


def test_insider_page_keeps_older_days_from_store(session) -> None:
    with (
        patch(
            "pms_platform.market_data.insider_store.fetch_insider_rows",
            side_effect=_fake_bse_insider,
        ),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset(),
        ),
        patch(
            "pms_platform.market_data.bse_corporate_disclosures._today_ist",
            return_value=date(2026, 8, 18),
        ),
        patch(
            "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
            return_value="500325",
        ),
    ):
        fetch_corporate_disclosures(
            "insider",
            session,
            calendar_month="2026-08",
            enrich_market_cap=False,
            refresh_insider=True,
        )
        session.commit()
        latest = fetch_corporate_disclosures(
            "insider",
            session,
            calendar_month="2026-08",
            enrich_market_cap=False,
        )
        older = fetch_corporate_disclosures(
            "insider",
            session,
            as_of_date=date(2026, 8, 11),
            calendar_month="2026-08",
            enrich_market_cap=False,
        )

    assert date(2026, 8, 11) in latest.available_dates
    assert date(2026, 8, 18) in latest.available_dates
    assert older.as_of_date == date(2026, 8, 11)
    assert len(older.rows) == 3


def test_insider_page_fetches_missing_days_without_refresh(session) -> None:
    """Page load fills calendar days that were never cached (stale cache after 20 Aug)."""
    session.add(
        InsiderDisclosureDay(
            disclosure_date=date(2026, 8, 20),
            rows=_insider_raw(date(2026, 8, 20), 2),
            row_count=2,
            truncated=False,
            fetched_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
    )
    session.commit()
    calls: list[date] = []

    def fake(from_date: date, to_date: date, scrip_code: str = "") -> list[dict]:
        calls.append(from_date)
        if scrip_code:
            return []
        if from_date >= date(2026, 8, 21):
            return _insider_raw(from_date, 2)
        return []

    with (
        patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake),
        patch(
            "pms_platform.market_data.insider_store.insider_backfill_bse_codes",
            return_value=frozenset(),
        ),
        patch(
            "pms_platform.market_data.bse_corporate_disclosures._today_ist",
            return_value=date(2026, 8, 24),
        ),
    ):
        result = fetch_corporate_disclosures(
            "insider",
            session,
            calendar_month="2026-08",
            enrich_market_cap=False,
        )

    assert date(2026, 8, 20) not in calls
    assert date(2026, 8, 21) in calls
    assert date(2026, 8, 24) in calls
    assert date(2026, 8, 24) in result.available_dates
    assert session.get(InsiderDisclosureDay, date(2026, 8, 24)) is not None
