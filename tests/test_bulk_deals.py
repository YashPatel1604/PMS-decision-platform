"""Unit tests for BSE bulk-deal normalize + fetch filtering."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pms_platform.market_data.bse_disclosed_deals import (
    fetch_disclosed_deals,
    normalize_disclosed_deals_frame,
)


def test_normalize_bulk_purchase_sell_codes() -> None:
    frame = [
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
    deals = normalize_disclosed_deals_frame(frame, kind="bulk")
    assert len(deals) == 2
    assert [d.deal_type for d in deals] == ["BUY", "SELL"]
    assert deals[0].deal_date == date(2026, 7, 1)
    assert deals[0].quantity == Decimal("2876465")


def test_normalize_nse_bulk_columns() -> None:
    frame = [
        {
            "Date ": "30-SEP-2026",
            "Symbol ": "AAREYDRUGS",
            "Security Name ": "Aarey Drugs & Pharm Ltd",
            "Client Name ": "ARYA RAVI MANIRAM",
            "Buy / Sell ": "BUY",
            "Quantity Traded ": "1,44,423",
            "Trade Price / Wght. Avg. Price ": "100.01",
            "Remarks ": "-",
        }
    ]
    deals = normalize_disclosed_deals_frame(frame, kind="bulk")
    assert len(deals) == 1
    assert deals[0].deal_date == date(2026, 9, 30)
    assert deals[0].bse_code == "AAREYDRUGS"
    assert deals[0].deal_type == "BUY"
    assert deals[0].quantity == Decimal("144423")
    assert deals[0].price == Decimal("100.01")


def test_rupee_market_cap_becomes_crores() -> None:
    from pms_platform.market_data.bse_disclosed_deals import (
        _market_cap_cr_from_screener_html,
        _parse_market_cap_cr,
    )

    # ₹2,000 Cr written out in rupees.
    assert _parse_market_cap_cr("20000000000") == Decimal("2000.00")
    # Already crores (under ₹1 Cr of rupees).
    assert _parse_market_cap_cr("1587299") == Decimal("1587299")
    html = (
        'Market Cap</span><span class="nowrap value">₹'
        '<span class="number">15,87,299</span> Cr.</span>'
    )
    assert _market_cap_cr_from_screener_html(html) == Decimal("1587299")


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
    frame = [
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
    latest = fetch_disclosed_deals("bulk", session=None, fetch_frame=lambda: frame)
    assert latest.as_of_date == date(2026, 7, 28)
    assert latest.deal_count == 1
    assert latest.kind == "bulk"
    assert latest.available_dates == (date(2026, 7, 28), date(2026, 7, 1))

    prior = fetch_disclosed_deals(
        "bulk",
        session=None,
        fetch_frame=lambda: frame,
        as_of_date=date(2026, 7, 1),
    )
    assert prior.deal_count == 1
    assert prior.deals[0].bse_code == "500112"
    assert latest.portfolio_dates == ()


def test_portfolio_dates_only_include_our_firms(session, sample_security) -> None:
    sample_security.bse_code = "500325"
    session.flush()
    frame = [
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
    result = fetch_disclosed_deals("bulk", session=session, fetch_frame=lambda: frame)
    assert result.available_dates == (date(2026, 7, 28), date(2026, 7, 1))
    assert result.portfolio_dates == (date(2026, 7, 28),)
