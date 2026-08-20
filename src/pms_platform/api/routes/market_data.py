"""Live market-data refresh and Yahoo search API routes."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.market_data.block_deals import (
    BlockDealsFetchError,
    fetch_todays_block_deals,
)
from pms_platform.market_data.bulk_deals import (
    BulkDealsFetchError,
    fetch_todays_bulk_deals,
)
from pms_platform.market_data.live_quotes import refresh_live_quotes
from pms_platform.market_data.yahoo_finance import YahooFinanceClient

router = APIRouter()


class LiveQuoteRefreshResponse(BaseModel):
    requested: int
    fetched: int
    upserted: int
    missing_symbol: int
    failed: int
    as_of_date: str
    tickers: list[str]
    notes: list[str]
    source: str = "YAHOO_FINANCE"
    prefer_bse: bool = True


class YahooSearchHitResponse(BaseModel):
    symbol: str
    name: str
    exchange: str
    yahoo_ticker: str


@router.post("/live-quotes/refresh", response_model=LiveQuoteRefreshResponse)
def refresh_open_live_quotes(
    prefer_bse: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> LiveQuoteRefreshResponse:
    """Fetch BSE (default) live quotes for open holdings and store today's marks."""
    try:
        result = refresh_live_quotes(session, prefer_bse=prefer_bse)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return LiveQuoteRefreshResponse(
        requested=result.requested,
        fetched=result.fetched,
        upserted=result.upserted,
        missing_symbol=result.missing_symbol,
        failed=result.failed,
        as_of_date=result.as_of_date.isoformat(),
        tickers=list(result.tickers),
        notes=list(result.notes),
        prefer_bse=prefer_bse,
    )


@router.get("/yahoo/search", response_model=list[YahooSearchHitResponse])
def yahoo_search(q: str = Query(..., min_length=1)) -> list[YahooSearchHitResponse]:
    """Typeahead search for Indian equities on Yahoo Finance."""
    try:
        hits = YahooFinanceClient().search(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        YahooSearchHitResponse(
            symbol=h.symbol,
            name=h.name,
            exchange=h.exchange,
            yahoo_ticker=h.yahoo_ticker,
        )
        for h in hits
    ]


class BlockDealResponse(BaseModel):
    deal_date: date | None
    bse_code: str
    scrip_name: str
    client_name: str
    deal_type: str
    quantity: Decimal
    price: Decimal
    value: Decimal
    is_arbitrage: bool
    portfolio_name: str | None = None
    in_portfolio: bool = False
    is_open: bool = False
    market_cap_cr: Decimal | None = None


class TodayBlockDealsResponse(BaseModel):
    as_of_date: date
    fetched_at: datetime
    deal_count: int
    arbitrage_deal_count: int
    non_arbitrage_deal_count: int
    available_dates: list[date]
    portfolio_dates: list[date] = []
    deals: list[BlockDealResponse]


def _block_deals_response(result: object) -> TodayBlockDealsResponse:
    from pms_platform.market_data.bse_disclosed_deals import DisclosedDealsResult

    assert isinstance(result, DisclosedDealsResult)
    return TodayBlockDealsResponse(
        as_of_date=result.as_of_date,
        fetched_at=result.fetched_at,
        deal_count=result.deal_count,
        arbitrage_deal_count=result.arbitrage_deal_count,
        non_arbitrage_deal_count=result.non_arbitrage_deal_count,
        available_dates=list(result.available_dates),
        portfolio_dates=list(result.portfolio_dates),
        deals=[
            BlockDealResponse(
                deal_date=d.deal_date,
                bse_code=d.bse_code,
                scrip_name=d.scrip_name,
                client_name=d.client_name,
                deal_type=d.deal_type,
                quantity=d.quantity,
                price=d.price,
                value=d.value,
                is_arbitrage=d.is_arbitrage,
                portfolio_name=d.portfolio_name,
                in_portfolio=d.in_portfolio,
                is_open=d.is_open,
                market_cap_cr=d.market_cap_cr,
            )
            for d in result.deals
        ],
    )


@router.get("/block-deals/today", response_model=TodayBlockDealsResponse)
def today_block_deals(
    date_value: date | None = Query(default=None, alias="date"),
    month: str | None = Query(
        default=None,
        description="Calendar month YYYY-MM used to grey days without block deals",
        pattern=r"^\d{4}-\d{2}$",
    ),
    session: Session = Depends(get_db),
) -> TodayBlockDealsResponse:
    """Fetch disclosed BSE block deals for a session date (default: latest)."""
    try:
        result = fetch_todays_block_deals(
            session, as_of_date=date_value, calendar_month=month
        )
    except BlockDealsFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _block_deals_response(result)


@router.get("/bulk-deals/today", response_model=TodayBlockDealsResponse)
def today_bulk_deals(
    date_value: date | None = Query(default=None, alias="date"),
    month: str | None = Query(
        default=None,
        description="Calendar month YYYY-MM used to grey days without bulk deals",
        pattern=r"^\d{4}-\d{2}$",
    ),
    session: Session = Depends(get_db),
) -> TodayBlockDealsResponse:
    """Fetch disclosed BSE bulk deals for a session date (default: latest)."""
    try:
        result = fetch_todays_bulk_deals(
            session, as_of_date=date_value, calendar_month=month
        )
    except BulkDealsFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _block_deals_response(result)


class CorporateDisclosureResponse(BaseModel):
    kind: str
    disclosure_date: date | None
    bse_code: str
    company_name: str
    person_name: str
    category: str
    transaction_type: str
    quantity: Decimal | None = None
    value: Decimal | None = None
    pct_pre: Decimal | None = None
    pct_post: Decimal | None = None
    mode: str
    regulation: str
    isin: str | None = None
    market_cap_cr: Decimal | None = None
    portfolio_name: str | None = None
    in_portfolio: bool = False
    is_open: bool = False
    is_arbitrage: bool = False


class TodayCorporateDisclosuresResponse(BaseModel):
    kind: str
    as_of_date: date
    fetched_at: datetime
    row_count: int
    available_dates: list[date]
    portfolio_dates: list[date] = []
    rows: list[CorporateDisclosureResponse]


def _corporate_disclosures_response(result: object) -> TodayCorporateDisclosuresResponse:
    from pms_platform.market_data.bse_corporate_disclosures import (
        CorporateDisclosuresResult,
    )

    assert isinstance(result, CorporateDisclosuresResult)
    return TodayCorporateDisclosuresResponse(
        kind=result.kind,
        as_of_date=result.as_of_date,
        fetched_at=result.fetched_at,
        row_count=result.row_count,
        available_dates=list(result.available_dates),
        portfolio_dates=list(result.portfolio_dates),
        rows=[
            CorporateDisclosureResponse(
                kind=r.kind,
                disclosure_date=r.disclosure_date,
                bse_code=r.bse_code,
                company_name=r.company_name,
                person_name=r.person_name,
                category=r.category,
                transaction_type=r.transaction_type,
                quantity=r.quantity,
                value=r.value,
                pct_pre=r.pct_pre,
                pct_post=r.pct_post,
                mode=r.mode,
                regulation=r.regulation,
                isin=r.isin,
                market_cap_cr=r.market_cap_cr,
                portfolio_name=r.portfolio_name,
                in_portfolio=r.in_portfolio,
                is_open=r.is_open,
                is_arbitrage=r.is_arbitrage,
            )
            for r in result.rows
        ],
    )


@router.get("/sast/today", response_model=TodayCorporateDisclosuresResponse)
def today_sast_disclosures(
    date_value: date | None = Query(default=None, alias="date"),
    month: str | None = Query(
        default=None,
        description="Calendar month YYYY-MM used to grey days without SAST disclosures",
        pattern=r"^\d{4}-\d{2}$",
    ),
    session: Session = Depends(get_db),
) -> TodayCorporateDisclosuresResponse:
    """BSE SAST system-driven disclosures (Regulation 29)."""
    from pms_platform.market_data.bse_corporate_disclosures import (
        CorporateDisclosuresFetchError,
        fetch_corporate_disclosures,
    )

    try:
        result = fetch_corporate_disclosures(
            "sast", session, as_of_date=date_value, calendar_month=month
        )
    except CorporateDisclosuresFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _corporate_disclosures_response(result)


@router.get("/insider-trading/today", response_model=TodayCorporateDisclosuresResponse)
def today_insider_trading(
    date_value: date | None = Query(default=None, alias="date"),
    month: str | None = Query(
        default=None,
        description="Calendar month YYYY-MM used to grey days without insider disclosures",
        pattern=r"^\d{4}-\d{2}$",
    ),
    refresh: bool = Query(
        default=False,
        description="When true, pull recent days from BSE before responding (slow; default reads DB cache)",
    ),
    session: Session = Depends(get_db),
) -> TodayCorporateDisclosuresResponse:
    """BSE Insider Trading 2015 disclosures submitted by company."""
    from pms_platform.market_data.bse_corporate_disclosures import (
        CorporateDisclosuresFetchError,
        fetch_corporate_disclosures,
    )

    try:
        result = fetch_corporate_disclosures(
            "insider",
            session,
            as_of_date=date_value,
            calendar_month=month,
            refresh_insider=refresh,
        )
    except CorporateDisclosuresFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _corporate_disclosures_response(result)
