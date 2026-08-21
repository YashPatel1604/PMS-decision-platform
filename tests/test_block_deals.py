"""Unit tests for BSE block-deal normalize + arbitrage flagging."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pms_platform.market_data.bse_disclosed_deals import (
    DisclosedDealRow as BlockDealRow,
    DisclosedDealsFetchError as BlockDealsFetchError,
    fetch_disclosed_deals,
    flag_arbitrage_deals,
    normalize_disclosed_deals_frame,
)


def _row(
    *,
    code: str = "500325",
    client: str = "ABC Capital",
    deal_type: str = "BUY",
    qty: str = "1000",
    price: str = "100",
    name: str = "RELIANCE",
) -> BlockDealRow:
    q = Decimal(qty)
    p = Decimal(price)
    return BlockDealRow(
        deal_date=date(2026, 8, 6),
        bse_code=code,
        scrip_name=name,
        client_name=client,
        deal_type=deal_type,
        quantity=q,
        price=p,
        value=q * p,
    )


def test_normalize_empty_frame() -> None:
    assert normalize_disclosed_deals_frame([], kind="block") == []
    assert normalize_disclosed_deals_frame(None, kind="block") == []


def test_normalize_standard_columns() -> None:
    frame = [
        {
            "Deal Date": "06-Aug-2026",
            "Security Code": "500325",
            "Security Name": "RELIANCE",
            "Client Name": "Foo Brokers",
            "Deal Type": "Buy",
            "Quantity": "1,000",
            "Price": "2,500.50",
        }
    ]
    deals = normalize_disclosed_deals_frame(frame, kind="block")
    assert len(deals) == 1
    deal = deals[0]
    assert deal.bse_code == "500325"
    assert deal.scrip_name == "RELIANCE"
    assert deal.client_name == "Foo Brokers"
    assert deal.deal_type == "BUY"
    assert deal.quantity == Decimal("1000")
    assert deal.price == Decimal("2500.50")
    assert deal.value == Decimal("2500500.00")
    assert deal.deal_date == date(2026, 8, 6)


def test_normalize_missing_required_columns_raises() -> None:
    frame = [{"Foo": 1, "Bar": 2}]
    with pytest.raises(BlockDealsFetchError):
        normalize_disclosed_deals_frame(frame, kind="block")


def test_arbitrage_same_firm_buy_and_sell() -> None:
    deals = [
        _row(deal_type="BUY", qty="1000"),
        _row(deal_type="SELL", qty="980"),
    ]
    flagged = flag_arbitrage_deals(deals)
    assert all(d.is_arbitrage for d in flagged)


def test_arbitrage_not_flagged_buy_only() -> None:
    deals = [
        _row(deal_type="BUY", qty="1000"),
        _row(deal_type="BUY", qty="500", client="Other Firm"),
    ]
    flagged = flag_arbitrage_deals(deals)
    assert not any(d.is_arbitrage for d in flagged)


def test_arbitrage_flagged_regardless_of_qty() -> None:
    deals = [
        _row(deal_type="BUY", qty="1000"),
        _row(deal_type="SELL", qty="1"),
    ]
    flagged = flag_arbitrage_deals(deals)
    assert all(d.is_arbitrage for d in flagged)


def test_arbitrage_different_firms_not_paired() -> None:
    deals = [
        _row(deal_type="BUY", qty="1000", client="Alpha"),
        _row(deal_type="SELL", qty="1000", client="Beta"),
    ]
    flagged = flag_arbitrage_deals(deals)
    assert not any(d.is_arbitrage for d in flagged)


def test_arbitrage_different_days_not_paired() -> None:
    deals = [
        _row(deal_type="BUY", qty="1000"),
        BlockDealRow(
            deal_date=date(2026, 8, 5),
            bse_code="500325",
            scrip_name="RELIANCE",
            client_name="ABC Capital",
            deal_type="SELL",
            quantity=Decimal("1000"),
            price=Decimal("100"),
            value=Decimal("100000"),
        ),
    ]
    flagged = flag_arbitrage_deals(deals)
    assert not any(d.is_arbitrage for d in flagged)


def test_normalize_purchase_code_p() -> None:
    frame = [
        {
            "Deal Date": "05/08/2026",
            "Security Code": "540565",
            "Company": "INDIGRID",
            "Client Name": "Foo",
            "Deal Type": "P",
            "Quantity": 1000,
            "Price": 150,
        },
        {
            "Deal Date": "05/08/2026",
            "Security Code": "540565",
            "Company": "INDIGRID",
            "Client Name": "Bar",
            "Deal Type": "S",
            "Quantity": 500,
            "Price": 151,
        },
    ]
    deals = normalize_disclosed_deals_frame(frame, kind="block")
    assert [d.deal_type for d in deals] == ["BUY", "SELL"]
    assert deals[0].deal_date == date(2026, 8, 5)


def test_fetch_todays_block_deals_with_mock_frame() -> None:
    frame = [
        {
            "Deal Date": "06-Aug-2026",
            "Security Code": "500325",
            "Security Name": "RELIANCE",
            "Client Name": "Arb Desk",
            "Deal Type": "Buy",
            "Quantity": 1000,
            "Price": 100,
        },
        {
            "Deal Date": "06-Aug-2026",
            "Security Code": "500325",
            "Security Name": "RELIANCE",
            "Client Name": "Arb Desk",
            "Deal Type": "Sell",
            "Quantity": 1000,
            "Price": 100.5,
        },
        {
            "Deal Date": "05-Aug-2026",
            "Security Code": "500112",
            "Security Name": "SBIN",
            "Client Name": "Other",
            "Deal Type": "Buy",
            "Quantity": 500,
            "Price": 800,
        },
    ]
    latest = fetch_disclosed_deals("block", session=None, fetch_frame=lambda: frame)
    assert latest.as_of_date == date(2026, 8, 6)
    assert latest.deal_count == 2
    assert latest.arbitrage_deal_count == 2
    assert latest.available_dates == (date(2026, 8, 6), date(2026, 8, 5))

    prior = fetch_disclosed_deals(
        "block",
        session=None,
        fetch_frame=lambda: frame,
        as_of_date=date(2026, 8, 5),
    )
    assert prior.as_of_date == date(2026, 8, 5)
    assert prior.deal_count == 1
    assert prior.deals[0].bse_code == "500112"
