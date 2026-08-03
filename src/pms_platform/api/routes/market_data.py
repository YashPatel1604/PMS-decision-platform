"""Live market-data refresh and Yahoo search API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
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
