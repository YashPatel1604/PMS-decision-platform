"""Compare-series and peer helpers for holdings split view."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from pms_platform.analytics.industry_peers import compute_industry_equal_weight
from pms_platform.analytics.portfolio_value import equity_portfolio_market_value
from pms_platform.analytics.successor_chain import resolve_price_security_id
from pms_platform.market_data.contracts import REQUIRED_BENCHMARKS
from pms_platform.market_data.yahoo_finance import YahooFinanceClient
from pms_platform.models import BenchmarkTri, DailyPrice, InvestmentEpisode, SecuritySuccessor

_HUNDRED = Decimal("100")
_ONE = Decimal("1")
_MAX_PEERS = 6
_SOURCE_PRIORITY = case(
    (DailyPrice.source == "YAHOO_CHART_REPAIR", 0),
    (DailyPrice.source.in_(frozenset({"YAHOO_FINANCE", "INDIAN_STOCK_API"})), 1),
    else_=2,
)


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


def _on_or_before(
    hist: list[tuple[date, Decimal]], day: date
) -> Decimal | None:
    """Last value on/before day from sorted (date, value) rows."""
    value = None
    for d, level in hist:
        if d <= day:
            value = level
        else:
            break
    return value


def _load_adj_close_series(
    session: Session, security_id: str, start: date, end: date
) -> list[tuple[date, Decimal]]:
    """One query: best-source adjusted close per trade date in [start, end]."""
    widened = date.fromordinal(max(start.toordinal() - 21, 1))
    rows = session.execute(
        select(DailyPrice.trade_date, DailyPrice.adjusted_close)
        .where(
            DailyPrice.security_id == security_id,
            DailyPrice.trade_date >= widened,
            DailyPrice.trade_date <= end,
        )
        .order_by(DailyPrice.trade_date, _SOURCE_PRIORITY, DailyPrice.source)
    ).all()
    best: dict[date, Decimal] = {}
    for trade_date, adj in rows:
        if trade_date not in best:
            best[trade_date] = adj
    return sorted(best.items())


def _load_benchmark_series(
    session: Session, benchmark_code: str, start: date, end: date
) -> list[tuple[date, Decimal]]:
    """One query: TRI levels in [start, end] (first source wins per date)."""
    widened = date.fromordinal(max(start.toordinal() - 21, 1))
    code = benchmark_code.strip().upper()
    rows = session.execute(
        select(BenchmarkTri.trade_date, BenchmarkTri.tri_level)
        .where(
            BenchmarkTri.benchmark_code == code,
            BenchmarkTri.trade_date >= widened,
            BenchmarkTri.trade_date <= end,
        )
        .order_by(BenchmarkTri.trade_date, BenchmarkTri.source)
    ).all()
    best: dict[date, Decimal] = {}
    for trade_date, level in rows:
        if trade_date not in best:
            best[trade_date] = level
    return sorted(best.items())


def _price_security_ids(
    session: Session, security_id: str, sample: list[date]
) -> dict[date, str]:
    """Map sample days → price security id without N successor queries when unused."""
    has_succ = (
        session.scalar(
            select(SecuritySuccessor.successor_id)
            .where(
                SecuritySuccessor.predecessor_security_id == security_id,
                SecuritySuccessor.confirmed.is_(True),
            )
            .limit(1)
        )
        is not None
    )
    if not has_succ:
        return {day: security_id for day in sample}
    return {day: resolve_price_security_id(session, security_id, day) for day in sample}


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
    start_px = _on_or_before(hist, start)
    if start_px is None:
        for day, price in hist:
            if day >= start:
                start_px = price
                break
    end_px = _on_or_before(hist, end) or (hist[-1][1] if hist else None)
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

    sid_by_day = _price_security_ids(session, security_id, sample)
    unique_sids = sorted(set(sid_by_day.values()))
    stock_series = {
        sid: _load_adj_close_series(session, sid, period_start, end_date)
        for sid in unique_sids
    }
    start_sid = sid_by_day[sample[0]] if sample else security_id
    stock_base = _on_or_before(stock_series.get(start_sid) or [], period_start)

    bench_code = REQUIRED_BENCHMARKS[0]
    bench_series = _load_benchmark_series(session, bench_code, period_start, end_date)
    bench_base = _on_or_before(bench_series, period_start)
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
        try:
            yahoo = client or YahooFinanceClient()
        except Exception as exc:  # noqa: BLE001
            yahoo = None
            notes.append(f"Yahoo client unavailable: {exc}")
        if yahoo is not None:
            for ticker in tickers:
                try:
                    hist, total = _peer_price_map(yahoo, ticker, period_start, end_date)
                    peer_hists[ticker] = hist
                    peer_returns[ticker] = total
                    base = _on_or_before(hist, period_start)
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
        sid = sid_by_day[day]
        stock_n = _normalize(_on_or_before(stock_series.get(sid) or [], day), stock_base)
        bench_n = _normalize(_on_or_before(bench_series, day), bench_base)
        port_n = _linear_normalized(day, period_start, end_date, port_return)
        industry_n = _linear_normalized(day, period_start, end_date, industry_return)

        peer_levels: dict[str, float | None] = {}
        for ticker in tickers:
            px = _on_or_before(peer_hists.get(ticker) or [], day)
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
