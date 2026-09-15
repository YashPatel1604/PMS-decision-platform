"""Assemble Pivot Point Strategy dashboard payload for one as-of date."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.market_data.nse_bhav_store import (
    available_trade_dates,
    bars_by_symbol,
    list_session_dates,
    load_day_bars,
    load_vol_exp_map,
    prior_session_date,
)
from pms_platform.market_data.pivot_derived import (
    FloorPivot,
    floor_pivot_levels,
    floor_pivots_for_symbols,
)
from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.nse_bhav import BhavImportRun, PivotPortfolioSymbol
from pms_platform.models.security import Security

# Excel Daily includes EQ + BE (trade-for-trade); other series stay out of Daily.
DAILY_SERIES = frozenset({"EQ", "BE"})
# Cash sleeve — not a pivot name.
HIDDEN_PIVOT_SYMBOLS = frozenset({"LIQUIDCASE"})


def open_holding_nse_symbols(session: Session) -> list[str]:
    """NSE tickers for Our holdings: open episodes ∪ Client Portfolio Model."""
    symbols: set[str] = set()
    rows = session.execute(
        select(Security.current_nse_symbol, Security.historical_nse_symbol)
        .join(InvestmentEpisode, InvestmentEpisode.security_id == Security.security_id)
        .where(InvestmentEpisode.status == EpisodeStatus.OPEN.value)
    ).all()
    for current, historical in rows:
        for raw in (current, historical):
            text = str(raw or "").strip().upper()
            if text and text not in {"NAN", "NONE", "NULL"}:
                symbols.add(text)
    # Julesh-only PCs have no episodes; Samir may still want Model names too.
    from pms_platform.domain.client_positions import resolve_client_portfolio_book

    book = resolve_client_portfolio_book(session)
    if book is not None:
        for pos in book.model:
            if pos.symbol:
                symbols.add(pos.symbol)
    symbols -= HIDDEN_PIVOT_SYMBOLS
    return sorted(symbols)


def _bar_dict(bar: Any) -> dict[str, Any]:
    return {
        "trade_date": bar.trade_date.isoformat(),
        "symbol": bar.symbol,
        "series": bar.series,
        "isin": bar.isin,
        "instrument_name": bar.instrument_name,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "prev_close": float(bar.prev_close) if bar.prev_close is not None else None,
        "volume": int(bar.volume or 0),
        "turnover": float(bar.turnover) if bar.turnover is not None else None,
    }


def _pivot_from_bar(bar: Any, *, as_of: date) -> dict[str, Any]:
    """Same-day floor pivots for one bhav row (EQ or BE)."""
    levels = floor_pivot_levels(bar.high, bar.low, bar.close)
    return FloorPivot(
        symbol=bar.symbol,
        series=bar.series,
        as_of=as_of,
        prior_date=bar.trade_date,
        prior_high=bar.high,
        prior_low=bar.low,
        prior_close=bar.close,
        last_close=bar.close,
        missing=False,
        **levels,
    ).as_dict()


def _daily_row(
    bar: Any,
    *,
    as_of: date,
    portfolio_a_by_symbol: dict[str, bool],
    vol_exp_by_symbol: dict[str, Decimal],
    prev_day_volume: int | None,
) -> dict[str, Any]:
    row = _bar_dict(bar)
    row["pivot"] = _pivot_from_bar(bar, as_of=as_of)
    if bar.symbol in portfolio_a_by_symbol:
        row["portfolio_flag"] = "Y" if portfolio_a_by_symbol[bar.symbol] else "N"
    else:
        row["portfolio_flag"] = None
    row["prev_day_volume"] = prev_day_volume
    vol_exp = vol_exp_by_symbol.get(bar.symbol)
    if vol_exp is not None:
        vol_15 = Decimal(vol_exp) / Decimal(25)
        row["vol_exp"] = float(vol_exp)
        row["vol_15min"] = float(vol_15)
        row["top50"] = float(vol_15 * Decimal(3))
        row["band_51_300"] = float(vol_15 * Decimal(6))
    else:
        row["vol_exp"] = None
        row["vol_15min"] = None
        row["top50"] = None
        row["band_51_300"] = None
    return row


def latest_committed_run(session: Session, trade_date: date | None = None) -> BhavImportRun | None:
    stmt = (
        select(BhavImportRun)
        .where(BhavImportRun.status == "committed")
        .order_by(BhavImportRun.committed_at.desc())
    )
    if trade_date is not None:
        stmt = stmt.where(BhavImportRun.trade_date == trade_date)
    return session.scalars(stmt.limit(1)).first()


def build_pivot_dashboard(
    session: Session,
    *,
    as_of: date | None = None,
    scope: str = "portfolio",
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Pivot strategy UI payload.

    Default ``scope=portfolio`` keeps egress tiny (UI default). ``scope=all`` returns
    the full Daily universe. ``last20`` / ``ranks`` / ``gainers`` are omitted from the
    wire payload — the React UI never read them and they were ~17MB/request.
    """
    dates = available_trade_dates(session)
    if as_of is None:
        as_of = dates[0] if dates else None
    if as_of is None:
        return {
            "as_of": None,
            "available_dates": [],
            "last_run": None,
            "daily": [],
            "last20": [],
            "ranks": [],
            "portfolio": [],
            "holding_symbols": [],
            "gainers": [],
            "session_dates": [],
            "scope": scope,
        }

    scope_key = (scope or "portfolio").strip().lower()
    selected = {s.strip().upper() for s in (symbols or []) if s and str(s).strip()}
    session_dates = list_session_dates(session, as_of=as_of, limit=20)
    # One day load (EQ+BE); do NOT pull the full Last20 window into the API response.
    daily = load_day_bars(session, as_of, series=None)
    vol_exp_by_symbol = load_vol_exp_map(session, as_of)
    prior_date = prior_session_date(session, as_of)

    portfolio_rows = list(
        session.scalars(
            select(PivotPortfolioSymbol).order_by(
                PivotPortfolioSymbol.sort_order,
                PivotPortfolioSymbol.symbol,
            )
        ).all()
    )
    portfolio_symbols = [p.symbol for p in portfolio_rows]
    portfolio_a_by_symbol = {p.symbol: p.portfolio_a for p in portfolio_rows}
    holding_symbols = open_holding_nse_symbols(session)
    holding_set = set(holding_symbols)

    last_map = bars_by_symbol([b for b in daily if b.series == "EQ"])
    for bar in daily:
        if bar.series == "BE":
            last_map.setdefault(bar.symbol, bar)

    prior_map: dict[str, Any] = {}
    prev_day_volume_by_key: dict[tuple[str, str], int] = {}
    if prior_date:
        prior_day_bars = load_day_bars(session, prior_date, series=None)
        for bar in prior_day_bars:
            if bar.series in DAILY_SERIES:
                prev_day_volume_by_key[(bar.symbol, bar.series)] = int(bar.volume or 0)
        prior_map = bars_by_symbol([b for b in prior_day_bars if b.series == "EQ"])
        for bar in prior_day_bars:
            if bar.series == "BE":
                prior_map.setdefault(bar.symbol, bar)

    if scope_key == "selected" and selected:
        wanted = selected | set(portfolio_symbols) | holding_set
    elif scope_key == "all":
        wanted = None  # full Daily
    else:
        # portfolio (default): Portfolio sheet ∪ Our holdings
        wanted = set(portfolio_symbols) | holding_set

    pivot_symbol_list = (
        sorted(wanted)
        if wanted is not None
        else list(
            dict.fromkeys(
                [
                    *portfolio_symbols,
                    *[b.symbol for b in daily if b.series in DAILY_SERIES],
                ]
            )
        )
    )
    pivots = {
        p.symbol: p
        for p in floor_pivots_for_symbols(
            as_of=as_of,
            symbols=pivot_symbol_list,
            prior_bars=prior_map,
            last_bars=last_map,
        )
    }

    portfolio_payload = []
    for member in portfolio_rows:
        if member.symbol in HIDDEN_PIVOT_SYMBOLS:
            continue
        pivot = pivots.get(member.symbol)
        portfolio_payload.append(
            {
                "symbol": member.symbol,
                "dummy": member.dummy,
                "portfolio_a": member.portfolio_a,
                "uptrend": member.uptrend,
                "support_note": member.support_note,
                "buy_note": member.buy_note,
                "sma_50": member.sma_50,
                "sma_100": member.sma_100,
                "sma_200": member.sma_200,
                "notes": member.notes,
                "pivot": pivot.as_dict() if pivot else None,
            }
        )

    daily_payload = []
    for bar in daily:
        if bar.series not in DAILY_SERIES or bar.symbol in HIDDEN_PIVOT_SYMBOLS:
            continue
        if wanted is not None and bar.symbol not in wanted:
            continue
        daily_payload.append(
            _daily_row(
                bar,
                as_of=as_of,
                portfolio_a_by_symbol=portfolio_a_by_symbol,
                vol_exp_by_symbol=vol_exp_by_symbol,
                prev_day_volume=prev_day_volume_by_key.get((bar.symbol, bar.series)),
            )
        )
        if len(daily_payload) >= 5000:
            break

    run = latest_committed_run(session, as_of)
    last_run = None
    if run is not None:
        # Omit validation/reconcile blobs from the hot path (can be large).
        last_run = {
            "run_id": run.run_id,
            "trade_date": run.trade_date.isoformat() if run.trade_date else None,
            "status": run.status,
            "source_filename": run.source_filename,
            "row_count_all": run.row_count_all,
            "row_count_eq": run.row_count_eq,
            "validation_report": {},
            "reconcile_report": {},
            "committed_at": run.committed_at.isoformat() if run.committed_at else None,
        }

    return {
        "as_of": as_of.isoformat(),
        "available_dates": [d.isoformat() for d in dates],
        "session_dates": [d.isoformat() for d in session_dates],
        "last_run": last_run,
        "daily": daily_payload,
        # Kept empty for API shape compatibility — never ship Last20 bars on the wire.
        "last20": [],
        "ranks": [],
        "portfolio": portfolio_payload,
        "holding_symbols": holding_symbols,
        "gainers": [],
        "scope": scope_key,
        "formulas": {
            "pivot": "PP=(H+L+C)/3 from same-day bhav (Excel Daily)",
            "s4": "L-3*(H-PP); S3=L-2*(H-PP); S2=PP-(H-L); S1=2*PP-H",
            "r4": "H+3*(PP-L); R3=H+2*(PP-L); R2=PP+(H-L); R1=2*PP-L",
            "bands": "Sx-0.3=Sx*(1-0.003); Rx+0.3=Rx*(1+0.003)",
            "vol_exp": "Last20 avg EQ vol ×1.1 (top 50 turnover) or ×1.2 (rest), snapshotted on commit",
            "vol_15min": "VolExp/25; Top50=15min×3; 51-300=15min×6",
            "prev_day_volume": "Prior session TtlTradgVol for same symbol+series",
            "portfolio": "Portfolio sheet PortfolioA (Y/N)",
            "retention": "Newest 21 bhav sessions kept in DB",
        },
    }
