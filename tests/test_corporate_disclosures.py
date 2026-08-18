"""Unit tests for BSE SAST / Insider disclosure normalization."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from pms_platform.market_data.bse_corporate_disclosures import (
    fetch_corporate_disclosures,
    normalize_insider_row,
    normalize_sast_row,
)
from pms_platform.market_data.insider_store import sync_insider_days
from pms_platform.models.insider_disclosure_day import InsiderDisclosureDay


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
    with patch(
        "pms_platform.market_data.bse_corporate_disclosures.resolve_bse_code",
        return_value="544444",
    ):
        row = normalize_insider_row(raw)
    assert row is not None
    assert row.kind == "insider"
    assert row.bse_code == "544444"
    assert row.disclosure_date == date(2026, 8, 6)
    assert row.value == Decimal("4966584.00")
    assert row.mode == "Market Purchase"


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


def test_insider_store_fetches_one_day_at_a_time(session) -> None:
    calls: list[tuple[date, date]] = []

    def fake(from_date: date, to_date: date) -> list[dict]:
        calls.append((from_date, to_date))
        return _fake_bse_insider(from_date, to_date)

    with patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake):
        fetched = sync_insider_days(
            session,
            date(2026, 8, 11),
            date(2026, 8, 18),
            today=date(2026, 8, 18),
        )
        session.commit()

    assert fetched == 8
    assert all(start == end for start, end in calls)
    older = session.get(InsiderDisclosureDay, date(2026, 8, 11))
    assert older is not None
    assert older.row_count == 3
    assert older.truncated is False
    today_row = session.get(InsiderDisclosureDay, date(2026, 8, 18))
    assert today_row is not None
    assert today_row.row_count == 25
    assert today_row.truncated is True

    calls.clear()
    with patch("pms_platform.market_data.insider_store.fetch_insider_rows", side_effect=fake):
        fetched_again = sync_insider_days(
            session,
            date(2026, 8, 11),
            date(2026, 8, 18),
            today=date(2026, 8, 18),
        )
    assert fetched_again == 1
    assert calls == [(date(2026, 8, 18), date(2026, 8, 18))]


def test_insider_page_keeps_older_days_from_store(session) -> None:
    with (
        patch(
            "pms_platform.market_data.insider_store.fetch_insider_rows",
            side_effect=_fake_bse_insider,
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
