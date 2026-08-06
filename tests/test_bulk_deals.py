"""Unit tests for BSE bulk-deal normalize + fetch filtering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from pms_platform.market_data.bulk_deals import (
    fetch_todays_bulk_deals,
    normalize_bulk_deals_frame,
)


def test_normalize_bulk_purchase_sell_codes() -> None:
    frame = pd.DataFrame(
        [
            {
                "Deal Date": "01/07/2026",
                "Security Code": "512591",
                "Company": "PULSRIN",
                "Client Name": "SHARE INDIA SECURITIES LIMITED",
                "Deal Type": "P",
                "Quantity": 2876465,
                "Price": 0.53,
            },
            {
                "Deal Date": "01/07/2026",
                "Security Code": "512591",
                "Company": "PULSRIN",
                "Client Name": "SHARE INDIA SECURITIES LIMITED",
                "Deal Type": "S",
                "Quantity": 3112309,
                "Price": 0.53,
            },
        ]
    )
    deals = normalize_bulk_deals_frame(frame)
    assert len(deals) == 2
    assert [d.deal_type for d in deals] == ["BUY", "SELL"]
    assert deals[0].deal_date == date(2026, 7, 1)
    assert deals[0].quantity == Decimal("2876465")


def test_filter_deals_by_market_cap() -> None:
    from pms_platform.market_data.bse_disclosed_deals import (
        DisclosedDealRow,
        filter_deals_by_market_cap,
    )

    deals = [
        DisclosedDealRow(
            deal_date=date(2026, 8, 5),
            bse_code="1",
            scrip_name="BIG",
            client_name="A",
            deal_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            value=Decimal("1"),
            market_cap_cr=Decimal("5000"),
        ),
        DisclosedDealRow(
            deal_date=date(2026, 8, 5),
            bse_code="2",
            scrip_name="SMALL",
            client_name="B",
            deal_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            value=Decimal("1"),
            market_cap_cr=Decimal("500"),
        ),
        DisclosedDealRow(
            deal_date=date(2026, 8, 5),
            bse_code="3",
            scrip_name="UNK",
            client_name="C",
            deal_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            value=Decimal("1"),
            market_cap_cr=None,
        ),
    ]
    kept = filter_deals_by_market_cap(deals, min_market_cap_cr=Decimal("2000"))
    assert [d.bse_code for d in kept] == ["1"]


def test_fetch_todays_bulk_deals_with_mock_frame() -> None:
    frame = pd.DataFrame(
        [
            {
                "Deal Date": "28/07/2026",
                "Security Code": "500325",
                "Company": "RELIANCE",
                "Client Name": "Alpha",
                "Deal Type": "P",
                "Quantity": 100000,
                "Price": 1400,
            },
            {
                "Deal Date": "01/07/2026",
                "Security Code": "500112",
                "Company": "SBIN",
                "Client Name": "Beta",
                "Deal Type": "S",
                "Quantity": 50000,
                "Price": 800,
            },
        ]
    )
    latest = fetch_todays_bulk_deals(session=None, fetch_frame=lambda: frame)
    assert latest.as_of_date == date(2026, 7, 28)
    assert latest.deal_count == 1
    assert latest.kind == "bulk"
    assert latest.available_dates == (date(2026, 7, 28), date(2026, 7, 1))

    prior = fetch_todays_bulk_deals(
        session=None,
        fetch_frame=lambda: frame,
        as_of_date=date(2026, 7, 1),
    )
    assert prior.deal_count == 1
    assert prior.deals[0].bse_code == "500112"
