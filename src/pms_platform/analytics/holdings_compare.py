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


def _peer_price_map(
    yahoo: YahooFinanceClient,
    ticker: str,
    start: date,
    end: date,
) -> tuple[dict[date, Decimal], Decimal | None]:
    """Daily closes on/before each day, plus total return over the window."""
    widened = date.fromordinal(max(start.toordinal() - 14, 1))
    try:
        history = yahoo.fetch_chart_history(ticker, widened, end)
    except Exception:  # noqa: BLE001
        return {}, None
    if not history:
        return {}, None

    # Forward-fill map for sample lookup: running last close
    running: Decimal | None = None
    filled: dict[date, Decimal] = {}
    cursor = widened
    hist_idx = 0
    hist = sorted(history)
    while cursor <= end:
        while hist_idx < len(hist) and hist[hist_idx][0] <= cursor:
            running = hist[hist_idx][1]
            hist_idx += 1
        if running is not None:
            filled[cursor] = running
        cursor = date.fromordinal(cursor.toordinal() + 1)

    start_px = None
    for day, price in reversed(hist):
        if day <= start:
            start_px = price
            break
    if start_px is None and hist:
        # first bar after start
        for day, price in hist:
            if day >= start:
                start_px = price
                break
    end_px = filled.get(end) or (hist[-1][1] if hist else None)
    total = None
    if start_px is not None and end_px is not None and start_px > 0:
        total = ((end_px / start_px) - _ONE) * _HUNDRED
    return filled, total


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

    port_base = equity_portfolio_market_value(session, period_start)

    industry = compute_industry_equal_weight(
        session,
        security_id=security_id,
        start_date=period_start,
        end_date=end_date,
        fetch_yahoo=False,
    )
    industry_return = industry.total_return_pct

    peer_returns: dict[str, Decimal | None] = {ticker: None for ticker in tickers}
    peer_price_maps: dict[str, dict[date, Decimal]] = {}
    peer_bases: dict[str, Decimal | None] = {}
    if tickers:
        yahoo = client or YahooFinanceClient()
        for ticker in tickers:
            try:
                price_map, total = _peer_price_map(yahoo, ticker, period_start, end_date)
                peer_price_maps[ticker] = price_map
                peer_returns[ticker] = total
                base = None
                for day in sorted(price_map):
                    if day <= period_start:
                        base = price_map[day]
                    else:
                        break
                if base is None and price_map:
                    # first available on/after start
                    for day in sorted(price_map):
                        if day >= period_start:
                            base = price_map[day]
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

        port_v = equity_portfolio_market_value(session, day)
        port_n = _normalize(port_v, port_base)

        industry_n = _linear_normalized(day, period_start, end_date, industry_return)

        peer_levels: dict[str, float | None] = {}
        for ticker in tickers:
            price_map = peer_price_maps.get(ticker) or {}
            # last close on/before sample day
            px = None
            for d in sorted(price_map):
                if d <= day:
                    px = price_map[d]
                else:
                    break
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
