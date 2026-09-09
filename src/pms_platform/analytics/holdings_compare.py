"""Compare-series and peer helpers for holdings split view."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from pms_platform.analytics.industry_peers import compute_industry_equal_weight
from pms_platform.analytics.portfolio_value import equity_portfolio_market_value
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.contracts import REQUIRED_BENCHMARKS
from pms_platform.market_data.lookup import lookup_benchmark_tri, lookup_daily_price
from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models import InvestmentEpisode

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_MAX_PEERS = 6


@dataclass(frozen=True)
class CompareSeriesPoint:
    trade_date: date
    stock: float | None
    bse_smallcap: float | None
    portfolio: float | None
    industry_ew: float | None
    peers: dict[str, float | None] = field(default_factory=dict)

    @property
    def peer(self) -> float | None:
        """First peer level (back-compat for single-peer clients)."""
        if not self.peers:
            return None
        return next(iter(self.peers.values()))


@dataclass(frozen=True)
class PeerSeriesSummary:
    ticker: str
    total_return_pct: Decimal | None


@dataclass(frozen=True)
class CompareSeriesResult:
    episode_id: int
    security_id: str
    start_date: date
    end_date: date
    points: tuple[CompareSeriesPoint, ...]
    industry_return_pct: Decimal | None
    peer_series: tuple[PeerSeriesSummary, ...]
    notes: tuple[str, ...]

    @property
    def peer_return_pct(self) -> Decimal | None:
        return self.peer_series[0].total_return_pct if self.peer_series else None

    @property
    def peer_ticker(self) -> str | None:
        return self.peer_series[0].ticker if self.peer_series else None


def _sample_dates(start: date, end: date, max_points: int = 80) -> list[date]:
    days = max((end - start).days, 0)
    if days <= max_points:
        return [start + timedelta(days=i) for i in range(days + 1)]
    step = max(days // max_points, 1)
    dates = [start + timedelta(days=i) for i in range(0, days + 1, step)]
    if dates[-1] != end:
        dates.append(end)
    return dates


def _normalize(level: Decimal | None, base: Decimal | None) -> float | None:
    if level is None or base is None or base <= 0:
        return None
    return float((level / base) * _HUNDRED)


def _normalize_peer_tickers(
    peer_tickers: list[str] | None,
    peer_ticker: str | None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in [*(peer_tickers or []), *([peer_ticker] if peer_ticker else [])]:
        for part in str(raw).split(","):
            ticker = part.strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            ordered.append(ticker)
            if len(ordered) >= _MAX_PEERS:
                return ordered
    return ordered


def _linear_normalized(
    day: date,
    start: date,
    end: date,
    total_return_pct: Decimal | None,
) -> float | None:
    """Interpolate 100 → 100*(1+r) across the window (for industry EW)."""
    if total_return_pct is None:
        return None
    end_level = float(_HUNDRED * (_ONE + total_return_pct / _HUNDRED))
    if day <= start:
        return 100.0
    if day >= end:
        return end_level
    span_days = max((end - start).days, 1)
    frac = (day - start).days / span_days
    return 100.0 + (end_level - 100.0) * frac


def _peer_price_on_or_before(
    hist: list[tuple[date, Decimal]], day: date
) -> Decimal | None:
    """Last close on/before day from sorted (date, close) bars."""
    px = None
    for d, price in hist:
        if d <= day:
            px = price
        else:
            break
    return px


def _peer_price_map(
    yahoo: YahooFinanceClient,
    ticker: str,
    start: date,
    end: date,
) -> tuple[list[tuple[date, Decimal]], Decimal | None]:
    """Yahoo daily closes plus total return over the window."""
    widened = date.fromordinal(max(start.toordinal() - 14, 1))
    try:
        history = yahoo.fetch_chart_history(ticker, widened, end)
    except Exception:  # noqa: BLE001
        return [], None
    if not history:
        return [], None

    hist = sorted(history)
    start_px = _peer_price_on_or_before(hist, start)
    if start_px is None:
        for day, price in hist:
            if day >= start:
                start_px = price
                break
    end_px = _peer_price_on_or_before(hist, end) or (hist[-1][1] if hist else None)
    total = None
    if start_px is not None and end_px is not None and start_px > 0:
        total = ((end_px / start_px) - _ONE) * _HUNDRED
    return hist, total


def build_compare_series(
    session: Session,
    *,
    episode_id: int,
    start_date: date,
    end_date: date,
    peer_ticker: str | None = None,
    peer_tickers: list[str] | None = None,
    client: YahooFinanceClient | None = None,
) -> CompareSeriesResult:
    episode = session.get(InvestmentEpisode, episode_id)
    notes: list[str] = []
    tickers = _normalize_peer_tickers(peer_tickers, peer_ticker)
    if episode is None:
        return CompareSeriesResult(
            episode_id=episode_id,
            security_id="",
            start_date=start_date,
            end_date=end_date,
            points=(),
            industry_return_pct=None,
            peer_series=tuple(PeerSeriesSummary(ticker=t, total_return_pct=None) for t in tickers),
            notes=("Episode not found",),
        )

    security_id = episode.security_id
    period_start = max(start_date, episode.entry_date)
    sample = _sample_dates(period_start, end_date)

    # Stock base
    price_id = resolve_price_security_id(session, security_id, period_start)
    stock_base_obs = lookup_daily_price(session, price_id, period_start)
    stock_base = stock_base_obs.adjusted_close if stock_base_obs else None

    bench_code = REQUIRED_BENCHMARKS[0]
    bench_base_obs = lookup_benchmark_tri(session, bench_code, period_start)
    bench_base = bench_base_obs.tri_level if bench_base_obs else None
    if bench_base is None:
        notes.append(f"No {bench_code} TRI at period start")

    # Portfolio path is O(holdings×lookups) per day — linearize from endpoints
    # like industry EW. Chart is provisional; headline uses the same endpoints.
    # ponytail: linear portfolio series (not true path); upgrade = batch MV cache.
    port_base = equity_portfolio_market_value(session, period_start)
    port_end = equity_portfolio_market_value(session, end_date)
    port_return: Decimal | None = None
    if port_base is not None and port_end is not None and port_base > 0:
        port_return = ((port_end / port_base) - _ONE) * _HUNDRED

    industry = compute_industry_equal_weight(
        session,
        security_id=security_id,
        start_date=period_start,
        end_date=end_date,
        fetch_yahoo=False,
    )
    industry_return = industry.total_return_pct
    if industry.peer_count == 0:
        notes.append(industry.notes[0] if industry.notes else "No industry peers")

    peer_returns: dict[str, Decimal | None] = {ticker: None for ticker in tickers}
    peer_hists: dict[str, list[tuple[date, Decimal]]] = {}
    peer_bases: dict[str, Decimal | None] = {}
    if tickers:
        yahoo = client or YahooFinanceClient()
        for ticker in tickers:
            try:
                hist, total = _peer_price_map(yahoo, ticker, period_start, end_date)
                peer_hists[ticker] = hist
                peer_returns[ticker] = total
                base = _peer_price_on_or_before(hist, period_start)
                if base is None and hist:
                    for day, price in hist:
                        if day >= period_start:
                            base = price
                            break
                peer_bases[ticker] = base
                if total is None:
                    notes.append(f"No Yahoo prices for peer {ticker}")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"Peer {ticker} fetch failed: {exc}")

    points: list[CompareSeriesPoint] = []
    for day in sample:
        sid = resolve_price_security_id(session, security_id, day)
        stock_obs = lookup_daily_price(session, sid, day)
        stock_n = _normalize(
            stock_obs.adjusted_close if stock_obs else None, stock_base
        )

        bench_obs = lookup_benchmark_tri(session, bench_code, day)
        bench_n = _normalize(bench_obs.tri_level if bench_obs else None, bench_base)

        port_n = _linear_normalized(day, period_start, end_date, port_return)
        industry_n = _linear_normalized(day, period_start, end_date, industry_return)

        peer_levels: dict[str, float | None] = {}
        for ticker in tickers:
            px = _peer_price_on_or_before(peer_hists.get(ticker) or [], day)
            peer_levels[ticker] = _normalize(px, peer_bases.get(ticker))

        points.append(
            CompareSeriesPoint(
                trade_date=day,
                stock=stock_n,
                bse_smallcap=bench_n,
                portfolio=port_n,
                industry_ew=industry_n,
                peers=peer_levels,
            )
        )

    return CompareSeriesResult(
        episode_id=episode_id,
        security_id=security_id,
        start_date=period_start,
        end_date=end_date,
        points=tuple(points),
        industry_return_pct=industry_return,
        peer_series=tuple(
            PeerSeriesSummary(ticker=ticker, total_return_pct=peer_returns.get(ticker))
            for ticker in tickers
        ),
        notes=tuple(notes),
    )


def peer_period_return(
    ticker: str,
    start: date,
    end: date,
    *,
    client: YahooFinanceClient | None = None,
):
    yahoo = client or YahooFinanceClient()
    return yahoo.period_return_detail(ticker, start, end)
