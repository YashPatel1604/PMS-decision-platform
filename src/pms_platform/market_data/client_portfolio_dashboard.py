"""Client Portfolio dashboard: Excel Model qty × Pivot bhav OHLC/pivots/Vol Exp."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from pms_platform.market_data.client_portfolio_parse import (
    book_meta,
    load_client_portfolio_book,
)
from pms_platform.market_data.nse_bhav_store import (
    available_trade_dates,
    load_day_bars,
    load_vol_exp_map,
)
from pms_platform.market_data.pivot_derived import FloorPivot, floor_pivot_levels
from pms_platform.market_data.pivot_dashboard import DAILY_SERIES, latest_committed_run


def _pivot_from_bar(bar: Any, *, as_of: date) -> dict[str, Any]:
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


def _pick_bar(eq_map: dict[str, Any], be_map: dict[str, Any], symbol: str) -> Any | None:
    return eq_map.get(symbol) or be_map.get(symbol)


def build_client_portfolio_dashboard(
    session: Session,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    dates = available_trade_dates(session)
    if as_of is None:
        as_of = dates[0] if dates else None

    book = load_client_portfolio_book()
    empty = {
        "as_of": as_of.isoformat() if as_of else None,
        "available_dates": [d.isoformat() for d in dates],
        "source_file": None,
        "excel_mtime": None,
        "excel_total_value": None,
        "bhav_revalued_total": None,
        "holdings": [],
        "missing_symbols": [],
        "model_symbols": [],
        "error": None,
    }
    if book is None:
        empty["error"] = (
            "PMS_ClientPortfolio.xlsx not found under Research/Portfolio "
            "(pin Always keep on this device)."
        )
        return empty
    if as_of is None:
        meta = book_meta(book)
        empty.update(meta)
        empty["model_symbols"] = [p.symbol for p in book.model]
        empty["error"] = "No bhav days committed yet — upload on Pivot Point Strategy."
        return empty

    eq_bars = {b.symbol: b for b in load_day_bars(session, as_of, series="EQ")}
    be_bars = {b.symbol: b for b in load_day_bars(session, as_of, series="BE")}
    vol_exp_by_symbol = load_vol_exp_map(session)

    holdings: list[dict[str, Any]] = []
    missing: list[str] = []
    revalued = Decimal(0)
    revalued_any = False

    for pos in book.model:
        bar = _pick_bar(eq_bars, be_bars, pos.symbol)
        stocks_qty = book.stocks_qty.get(pos.symbol)
        qty_mismatch = stocks_qty is not None and stocks_qty != pos.qty

        row: dict[str, Any] = {
            "symbol": pos.symbol,
            "qty": float(pos.qty),
            "stocks_qty": float(stocks_qty) if stocks_qty is not None else None,
            "qty_mismatch": qty_mismatch,
            "excel_price": float(pos.excel_price) if pos.excel_price is not None else None,
            "excel_value": float(pos.excel_value) if pos.excel_value is not None else None,
            "excel_percent": float(pos.excel_percent)
            if pos.excel_percent is not None
            else None,
            "index_label": pos.index_label,
            "series": None,
            "close": None,
            "bhav_value": None,
            "be_only": False,
            "missing_bhav": bar is None,
            "pivot": None,
            "vol_exp": None,
            "vol_15min": None,
            "top50": None,
            "band_51_300": None,
        }

        if bar is None:
            missing.append(pos.symbol)
            holdings.append(row)
            continue

        if bar.series not in DAILY_SERIES:
            missing.append(pos.symbol)
            holdings.append(row)
            continue

        close = Decimal(bar.close)
        bhav_value = pos.qty * close
        revalued += bhav_value
        revalued_any = True
        vol_exp = vol_exp_by_symbol.get(pos.symbol)
        row.update(
            {
                "series": bar.series,
                "close": float(close),
                "bhav_value": float(bhav_value),
                "be_only": bar.series == "BE",
                "pivot": _pivot_from_bar(bar, as_of=as_of),
            }
        )
        if vol_exp is not None:
            vol_15 = Decimal(vol_exp) / Decimal(25)
            row["vol_exp"] = float(vol_exp)
            row["vol_15min"] = float(vol_15)
            row["top50"] = float(vol_15 * Decimal(3))
            row["band_51_300"] = float(vol_15 * Decimal(6))
        holdings.append(row)

    run = latest_committed_run(session, as_of)
    last_run = None
    if run is not None:
        last_run = {
            "run_id": run.run_id,
            "trade_date": run.trade_date.isoformat() if run.trade_date else None,
            "status": run.status,
            "source_filename": run.source_filename,
        }

    meta = book_meta(book)
    return {
        "as_of": as_of.isoformat(),
        "available_dates": [d.isoformat() for d in dates],
        "source_file": meta["source_file"],
        "excel_mtime": meta["excel_mtime"],
        "excel_total_value": meta["excel_total_value"],
        "bhav_revalued_total": float(revalued) if revalued_any else None,
        "holdings": holdings,
        "missing_symbols": missing,
        "model_symbols": [p.symbol for p in book.model],
        "last_run": last_run,
        "error": None,
        "formulas": {
            "qty": "Model!Qnty from Research PMS_ClientPortfolio.xlsx",
            "close": "Committed NSE bhav (EQ preferred, else BE)",
            "pivot": "Same-day PP=(H+L+C)/3 + 0.3% bands (Pivot Daily)",
            "vol_exp": "Pivot Vol Exp table (AllSymbols seed or Last20×1.1)",
        },
    }
