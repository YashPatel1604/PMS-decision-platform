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
    load_bars_for_dates,
    load_day_bars,
    load_vol_exp_map,
    prior_session_date,
)
from pms_platform.market_data.pivot_derived import (
    FloorPivot,
    floor_pivot_levels,
    floor_pivots_for_symbols,
    gainer_rows,
    volume_ranks,
)
from pms_platform.models.enums import EpisodeStatus
from pms_platform.models.episode import InvestmentEpisode
from pms_platform.models.nse_bhav import BhavImportRun, PivotPortfolioSymbol
from pms_platform.models.security import Security

# Excel Daily includes EQ + BE (trade-for-trade); other series stay out of Daily.
DAILY_SERIES = frozenset({"EQ", "BE"})


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
    from pms_platform.market_data.client_portfolio_parse import load_client_portfolio_book

    book = load_client_portfolio_book()
    if book is not None:
        for pos in book.model:
            if pos.symbol:
                symbols.add(pos.symbol)
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
    prev_vol_exp_by_symbol: dict[str, Decimal],
) -> dict[str, Any]:
    row = _bar_dict(bar)
    row["pivot"] = _pivot_from_bar(bar, as_of=as_of)
    if bar.symbol in portfolio_a_by_symbol:
        row["portfolio_flag"] = "Y" if portfolio_a_by_symbol[bar.symbol] else "N"
    else:
        row["portfolio_flag"] = None
    prev_ve = prev_vol_exp_by_symbol.get(bar.symbol)
    row["prev_day_vol_exp"] = float(prev_ve) if prev_ve is not None else None
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
) -> dict[str, Any]:
    """Full tab payload for the pivot strategy UI."""
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
        }

    session_dates = list_session_dates(session, as_of=as_of, limit=20)
    daily = load_day_bars(session, as_of, series=None)
    last20 = load_bars_for_dates(session, session_dates, series="EQ")
    ranks = volume_ranks(last20, series="EQ")
    gainers = gainer_rows(load_day_bars(session, as_of, series="EQ"), series="EQ")
    # Daily Vol Exp = Last20 avg×1.1/1.2 snapshotted for this as_of (Excel Last20Days roll).
    vol_exp_by_symbol = load_vol_exp_map(session, as_of)
    prior_date = prior_session_date(session, as_of)
    prev_vol_exp_by_symbol = (
        load_vol_exp_map(session, prior_date) if prior_date is not None else {}
    )

    portfolio_rows = list(
        session.scalars(select(PivotPortfolioSymbol).order_by(PivotPortfolioSymbol.symbol)).all()
    )
    symbols = [p.symbol for p in portfolio_rows]
    # Prefer EQ bar per symbol; fall back to BE so BE-only names still get portfolio pivots.
    last_map = bars_by_symbol(load_day_bars(session, as_of, series="EQ"))
    for bar in load_day_bars(session, as_of, series="BE"):
        last_map.setdefault(bar.symbol, bar)
    prior_map: dict[str, Any] = {}
    if prior_date:
        prior_day_bars = load_day_bars(session, prior_date, series=None)
        prior_map = bars_by_symbol([b for b in prior_day_bars if b.series == "EQ"])
        for bar in prior_day_bars:
            if bar.series == "BE":
                prior_map.setdefault(bar.symbol, bar)

    daily_symbols = sorted({b.symbol for b in daily if b.series in DAILY_SERIES})
    pivot_symbol_list = list(dict.fromkeys([*symbols, *daily_symbols]))
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

    portfolio_a_by_symbol = {p.symbol: p.portfolio_a for p in portfolio_rows}
    holding_symbols = open_holding_nse_symbols(session)
    holding_set = set(holding_symbols)

    daily_payload = []
    for bar in daily:
        if bar.series not in DAILY_SERIES:
            continue
        daily_payload.append(
            _daily_row(
                bar,
                as_of=as_of,
                portfolio_a_by_symbol=portfolio_a_by_symbol,
                vol_exp_by_symbol=vol_exp_by_symbol,
                prev_vol_exp_by_symbol=prev_vol_exp_by_symbol,
            )
        )
        if len(daily_payload) >= 5000:
            break

    # Cap can drop late-alphabet holdings; pin Our holdings rows back in.
    present = {(r["symbol"], r["series"]) for r in daily_payload}
    for bar in daily:
        if bar.series not in DAILY_SERIES or bar.symbol not in holding_set:
            continue
        key = (bar.symbol, bar.series)
        if key in present:
            continue
        daily_payload.append(
            _daily_row(
                bar,
                as_of=as_of,
                portfolio_a_by_symbol=portfolio_a_by_symbol,
                vol_exp_by_symbol=vol_exp_by_symbol,
                prev_vol_exp_by_symbol=prev_vol_exp_by_symbol,
            )
        )
        present.add(key)

    run = latest_committed_run(session, as_of)
    last_run = None
    if run is not None:
        last_run = {
            "run_id": run.run_id,
            "trade_date": run.trade_date.isoformat() if run.trade_date else None,
            "status": run.status,
            "source_filename": run.source_filename,
            "row_count_all": run.row_count_all,
            "row_count_eq": run.row_count_eq,
            "validation_report": run.validation_report,
            "reconcile_report": run.reconcile_report,
            "committed_at": run.committed_at.isoformat() if run.committed_at else None,
        }

    return {
        "as_of": as_of.isoformat(),
        "available_dates": [d.isoformat() for d in dates],
        "session_dates": [d.isoformat() for d in session_dates],
        "last_run": last_run,
        "daily": daily_payload,
        "last20": [_bar_dict(b) for b in last20],
        "ranks": [r.as_dict() for r in ranks],
        "portfolio": portfolio_payload,
        "holding_symbols": holding_symbols,
        "gainers": [g.as_dict() for g in gainers],
        "formulas": {
            "pivot": "PP=(H+L+C)/3 from same-day bhav (Excel Daily)",
            "s4": "L-3*(H-PP); S3=L-2*(H-PP); S2=PP-(H-L); S1=2*PP-H",
            "r4": "H+3*(PP-L); R3=H+2*(PP-L); R2=PP+(H-L); R1=2*PP-L",
            "bands": "Sx-0.3=Sx*(1-0.003); Rx+0.3=Rx*(1+0.003)",
            "vol_exp": "Last20 avg EQ vol ×1.1 (top 50 turnover) or ×1.2 (rest), snapshotted on commit",
            "prev_day_vol_exp": "Vol Exp snapshot from the prior bhav day (what Daily showed yesterday)",
            "vol_15min": "VolExp/25",
            "top50": "15minVol*3",
            "band_51_300": "15minVol*6",
            "portfolio": "Portfolio sheet PortfolioA (Y/N)",
            "retention": "Only newest 20 trade sessions kept in DB",
        },
    }
