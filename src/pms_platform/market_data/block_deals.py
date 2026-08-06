"""BSE block deals — thin wrapper over shared disclosed-deals module."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from pms_platform.market_data.bse_disclosed_deals import (
    DisclosedDealRow as BlockDealRow,
    DisclosedDealsFetchError as BlockDealsFetchError,
    DisclosedDealsResult as BlockDealsResult,
    enrich_with_portfolio,
    fetch_disclosed_deals,
    flag_arbitrage_deals,
    normalize_client_name,
    normalize_disclosed_deals_frame,
)

__all__ = [
    "BlockDealRow",
    "BlockDealsFetchError",
    "BlockDealsResult",
    "enrich_with_portfolio",
    "fetch_todays_block_deals",
    "flag_arbitrage_deals",
    "normalize_block_deals_frame",
    "normalize_client_name",
]


def normalize_block_deals_frame(frame: Any) -> list[BlockDealRow]:
    return normalize_disclosed_deals_frame(frame, kind="block")


def fetch_todays_block_deals(
    session: Session | None = None,
    *,
    fetch_frame: Callable[[], Any] | None = None,
    as_of_date: date | None = None,
    calendar_month: str | None = None,
) -> BlockDealsResult:
    """Fetch BSE block deals for a session date with month availability."""
    return fetch_disclosed_deals(
        "block",
        session,
        fetch_frame=fetch_frame,
        as_of_date=as_of_date,
        calendar_month=calendar_month,
    )
