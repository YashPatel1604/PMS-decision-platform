"""Open holdings API routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pms_platform.analytics.holdings_compare import build_compare_series, peer_period_return
from pms_platform.analytics.industry_peers import compute_industry_equal_weight
from pms_platform.analytics.open_holdings import (
    OpenHoldingRow,
    OpenHoldingsResult,
    analyze_open_holdings,
)
from pms_platform.api.routes.episodes import get_db
from pms_platform.models import InvestmentEpisode

router = APIRouter()


class HoldingBenchmarkResponse(BaseModel):
    code: str
    total_return_pct: float | None
    excess_vs_stock_pp: float | None
    start_level: float | None
    end_level: float | None
    data_status: str


class OpenHoldingResponse(BaseModel):
    episode_id: int
    security_id: str
    portfolio_name: str
    entry_date: str
    as_of_date: str
    period_start_date: str
    quantity: int
    average_buy_price: float | None
    first_buy_price: float | None
    from_price: float | None
    from_price_date: str | None
    as_of_price: float | None
    as_of_price_date: str | None
    market_value: float | None
    cost_basis_value: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    stock_return_pct: float | None
    portfolio_return_pct: float | None
    excess_vs_portfolio_pp: float | None
    bse_return_pct: float | None
    excess_vs_bse_pp: float | None
    holding_days: int
    period_days: int
    position_weight_pct: float | None
    underwater: bool
    days_below_first_buy: int | None
    sector: str | None
    industry: str | None
    benchmarks: list[HoldingBenchmarkResponse]
    data_quality_status: str
    notes: list[str]


class LiveRefreshSummary(BaseModel):
    requested: int
    fetched: int
    upserted: int
    missing_symbol: int
    failed: int
    as_of_date: str
    notes: list[str]
    source: str
    prefer_bse: bool


class OpenHoldingsResponse(BaseModel):
    as_of_date: str
    from_date: str | None
    open_count: int
    equity_market_value: float | None
    equity_market_value_from: float | None = None
    reconstructed_equity_market_value: float | None = None
    reconstructed_equity_market_value_from: float | None = None
    portfolio_value_source: str | None = None
    portfolio_value_from_source: str | None = None
    portfolio_value_observation_date: str | None = None
    portfolio_value_from_observation_date: str | None = None
    portfolio_value_check_delta: float | None = None
    portfolio_value_from_check_delta: float | None = None
    portfolio_return_pct: float | None
    mean_excess_vs_primary_pp: float | None
    mean_excess_vs_portfolio_pp: float | None
    primary_benchmark_code: str
    benchmark_codes: list[str]
    holdings: list[OpenHoldingResponse]
    live_refresh: LiveRefreshSummary | None = None


class IndustryPeerResponse(BaseModel):
    security_id: str
    portfolio_name: str
    total_return_pct: float | None
    data_status: str


class IndustryCompareResponse(BaseModel):
    security_id: str
    industry: str | None
    peer_count: int
    used_count: int
    total_return_pct: float | None
    peers: list[IndustryPeerResponse]
    notes: list[str]


class PeerCompareResponse(BaseModel):
    ticker: str
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    total_return_pct: float


class CompareSeriesPointResponse(BaseModel):
    trade_date: str
    stock: float | None
    bse_smallcap: float | None
    portfolio: float | None
    industry_ew: float | None
    peer: float | None = None
    peers: dict[str, float | None] = {}


class PeerSeriesSummaryResponse(BaseModel):
    ticker: str
    total_return_pct: float | None


class CompareSeriesResponse(BaseModel):
    episode_id: int
    security_id: str
    start_date: str
    end_date: str
    points: list[CompareSeriesPointResponse]
    industry_return_pct: float | None
    peer_return_pct: float | None = None
    peer_ticker: str | None = None
    peer_series: list[PeerSeriesSummaryResponse] = []
    notes: list[str]


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _holding_response(row: OpenHoldingRow) -> OpenHoldingResponse:
    return OpenHoldingResponse(
        episode_id=row.episode_id,
        security_id=row.security_id,
        portfolio_name=row.portfolio_name,
        entry_date=row.entry_date.isoformat(),
        as_of_date=row.as_of_date.isoformat(),
        period_start_date=row.period_start_date.isoformat(),
        quantity=row.quantity,
        average_buy_price=_float(row.average_buy_price),
        first_buy_price=_float(row.first_buy_price),
        from_price=_float(row.from_price),
        from_price_date=(
            row.from_price_date.isoformat() if row.from_price_date else None
        ),
        as_of_price=_float(row.as_of_price),
        as_of_price_date=(
            row.as_of_price_date.isoformat() if row.as_of_price_date else None
        ),
        market_value=_float(row.market_value),
        cost_basis_value=_float(row.cost_basis_value),
        unrealized_pnl=_float(row.unrealized_pnl),
        unrealized_pnl_pct=_float(row.unrealized_pnl_pct),
        stock_return_pct=_float(row.stock_return_pct),
        portfolio_return_pct=_float(row.portfolio_return_pct),
        excess_vs_portfolio_pp=_float(row.excess_vs_portfolio_pp),
        bse_return_pct=_float(row.bse_return_pct),
        excess_vs_bse_pp=_float(row.excess_vs_bse_pp),
        holding_days=row.holding_days,
        period_days=row.period_days,
        position_weight_pct=_float(row.position_weight_pct),
        underwater=row.underwater,
        days_below_first_buy=row.days_below_first_buy,
        sector=row.sector,
        industry=row.industry,
        benchmarks=[
            HoldingBenchmarkResponse(
                code=item.code,
                total_return_pct=_float(item.total_return_pct),
                excess_vs_stock_pp=_float(item.excess_vs_stock_pp),
                start_level=_float(item.start_level),
                end_level=_float(item.end_level),
                data_status=item.data_status,
            )
            for item in row.benchmarks
        ],
        data_quality_status=row.data_quality_status,
        notes=list(row.notes),
    )


def _result_response(result: OpenHoldingsResult) -> OpenHoldingsResponse:
    live = None
    if result.live_refresh is not None:
        live = LiveRefreshSummary(
            requested=int(result.live_refresh["requested"]),
            fetched=int(result.live_refresh["fetched"]),
            upserted=int(result.live_refresh["upserted"]),
            missing_symbol=int(result.live_refresh["missing_symbol"]),
            failed=int(result.live_refresh["failed"]),
            as_of_date=str(result.live_refresh["as_of_date"]),
            notes=list(result.live_refresh["notes"]),  # type: ignore[arg-type]
            source=str(result.live_refresh["source"]),
            prefer_bse=bool(result.live_refresh["prefer_bse"]),
        )
    return OpenHoldingsResponse(
        as_of_date=result.as_of_date.isoformat(),
        from_date=result.from_date.isoformat() if result.from_date else None,
        open_count=result.open_count,
        equity_market_value=_float(result.equity_market_value),
        equity_market_value_from=_float(result.equity_market_value_from),
        reconstructed_equity_market_value=_float(result.reconstructed_equity_market_value),
        reconstructed_equity_market_value_from=_float(
            result.reconstructed_equity_market_value_from
        ),
        portfolio_value_source=result.portfolio_value_source,
        portfolio_value_from_source=result.portfolio_value_from_source,
        portfolio_value_observation_date=(
            result.portfolio_value_observation_date.isoformat()
            if result.portfolio_value_observation_date
            else None
        ),
        portfolio_value_from_observation_date=(
            result.portfolio_value_from_observation_date.isoformat()
            if result.portfolio_value_from_observation_date
            else None
        ),
        portfolio_value_check_delta=_float(result.portfolio_value_check_delta),
        portfolio_value_from_check_delta=_float(result.portfolio_value_from_check_delta),
        portfolio_return_pct=_float(result.portfolio_return_pct),
        mean_excess_vs_primary_pp=_float(result.mean_excess_vs_primary_pp),
        mean_excess_vs_portfolio_pp=_float(result.mean_excess_vs_portfolio_pp),
        primary_benchmark_code=result.primary_benchmark_code,
        benchmark_codes=list(result.benchmark_codes),
        holdings=[_holding_response(row) for row in result.holdings],
        live_refresh=live,
    )


def _resolve_period(
    session: Session,
    episode: InvestmentEpisode,
    as_of: date | None,
    from_date: date | None,
) -> tuple[date, date]:
    from pms_platform.analytics.open_holdings import latest_holdings_as_of

    ceiling = latest_holdings_as_of(session)
    if as_of is None:
        end = ceiling or date.today()
    elif ceiling is not None and as_of > ceiling:
        end = ceiling
    else:
        end = as_of
    start = from_date if from_date is not None else episode.entry_date
    start = max(start, episode.entry_date)
    if start > end:
        raise HTTPException(status_code=400, detail="from_date is after as_of")
    return start, end


@router.get("/open", response_model=OpenHoldingsResponse)
def list_open_holdings(
    as_of: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    benchmarks: str | None = Query(default=None),
    refresh_live: bool = Query(
        default=False,
        description="Ignored: Holdings use Research books + committed bhav (no Yahoo).",
    ),
    session: Session = Depends(get_db),
) -> OpenHoldingsResponse:
    """List open holdings valued through latest History book or bhav day."""
    del refresh_live
    try:
        result = analyze_open_holdings(
            session,
            as_of_date=as_of,
            from_date=from_date,
            benchmarks=benchmarks,
            refresh_live=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _result_response(result)


@router.get("/open/{episode_id}", response_model=OpenHoldingResponse)
def get_open_holding(
    episode_id: int,
    as_of: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    benchmarks: str | None = Query(default=None),
    refresh_live: bool = Query(
        default=False,
        description="Ignored: Current Holdings are Excel/book only (no Yahoo).",
    ),
    session: Session = Depends(get_db),
) -> OpenHoldingResponse:
    """Return one open holding valued through an as-of date."""
    del refresh_live
    try:
        result = analyze_open_holdings(
            session,
            as_of_date=as_of,
            from_date=from_date,
            benchmarks=benchmarks,
            episode_id=episode_id,
            refresh_live=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.holdings:
        raise HTTPException(status_code=404, detail="Open holding not found")
    return _holding_response(result.holdings[0])


@router.get(
    "/open/{episode_id}/industry-compare",
    response_model=IndustryCompareResponse,
)
def industry_compare(
    episode_id: int,
    as_of: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    fetch_yahoo: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> IndustryCompareResponse:
    episode = session.get(InvestmentEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Open holding not found")
    start, end = _resolve_period(session, episode, as_of, from_date)
    result = compute_industry_equal_weight(
        session,
        security_id=episode.security_id,
        start_date=start,
        end_date=end,
        fetch_yahoo=fetch_yahoo,
    )
    return IndustryCompareResponse(
        security_id=result.security_id,
        industry=result.industry,
        peer_count=result.peer_count,
        used_count=result.used_count,
        total_return_pct=_float(result.total_return_pct),
        peers=[
            IndustryPeerResponse(
                security_id=p.security_id,
                portfolio_name=p.portfolio_name,
                total_return_pct=_float(p.total_return_pct),
                data_status=p.data_status,
            )
            for p in result.peers
        ],
        notes=list(result.notes),
    )


@router.get("/compare/peer", response_model=PeerCompareResponse)
def compare_peer(
    ticker: str = Query(..., min_length=1),
    as_of: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
) -> PeerCompareResponse:
    end = as_of or date.today()
    start = from_date or end
    if start > end:
        raise HTTPException(status_code=400, detail="from_date is after as_of")
    detail = peer_period_return(ticker.strip().upper(), start, end)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No Yahoo prices for {ticker}")
    return PeerCompareResponse(
        ticker=detail.ticker,
        start_date=detail.start_date.isoformat(),
        end_date=detail.end_date.isoformat(),
        start_price=float(detail.start_price),
        end_price=float(detail.end_price),
        total_return_pct=float(detail.total_return_pct),
    )


@router.get(
    "/open/{episode_id}/compare-series",
    response_model=CompareSeriesResponse,
)
def compare_series(
    episode_id: int,
    as_of: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    peer_ticker: str | None = Query(default=None),
    peer_tickers: list[str] | None = Query(default=None),
    session: Session = Depends(get_db),
) -> CompareSeriesResponse:
    episode = session.get(InvestmentEpisode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Open holding not found")
    start, end = _resolve_period(session, episode, as_of, from_date)
    result = build_compare_series(
        session,
        episode_id=episode_id,
        start_date=start,
        end_date=end,
        peer_ticker=peer_ticker,
        peer_tickers=peer_tickers,
    )
    return CompareSeriesResponse(
        episode_id=result.episode_id,
        security_id=result.security_id,
        start_date=result.start_date.isoformat(),
        end_date=result.end_date.isoformat(),
        points=[
            CompareSeriesPointResponse(
                trade_date=p.trade_date.isoformat(),
                stock=p.stock,
                bse_smallcap=p.bse_smallcap,
                portfolio=p.portfolio,
                industry_ew=p.industry_ew,
                peer=p.peer,
                peers=dict(p.peers),
            )
            for p in result.points
        ],
        industry_return_pct=_float(result.industry_return_pct),
        peer_return_pct=_float(result.peer_return_pct),
        peer_ticker=result.peer_ticker,
        peer_series=[
            PeerSeriesSummaryResponse(
                ticker=item.ticker,
                total_return_pct=_float(item.total_return_pct),
            )
            for item in result.peer_series
        ],
        notes=list(result.notes),
    )
